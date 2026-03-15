/*
 * monitor.c — read stdin, classify agent state, serve over Unix socket + HTTP.
 *
 * Usage:
 *   ./monitor --agent claude --socket /tmp/mysession.sock [--http-port 9000]
 *   echo status | nc -U /tmp/mysession.sock
 *   curl localhost:9000/status
 *
 * Compile: cc -O2 -o monitor monitor.c -lpthread
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <pthread.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <netinet/in.h>
#include <unistd.h>
#include <signal.h>
#include <time.h>

#define MAX_LOG   500
#define MAX_LINE  1024
#define RESP_MAX  (MAX_LINE * 55)   /* enough for 50 log lines JSON-encoded */

/* States */
typedef enum { ST_UNKNOWN, ST_WORKING, ST_IDLE, ST_RATE_LIMITED, ST_ERROR } State;
static const char *STATE_STR[] = { "unknown", "working", "idle", "rate_limited", "error" };

/* Pattern table — case-insensitive substring match */
typedef struct { const char *agent; State state; const char *pat; } Pat;
static const Pat PATS[] = {
    /* claude */
    {"claude", ST_WORKING,      "esc to cancel"},
    {"claude", ST_WORKING,      "✻"},
    {"claude", ST_WORKING,      "✽"},
    {"claude", ST_WORKING,      "✢"},
    {"claude", ST_WORKING,      "✳"},
    {"claude", ST_WORKING,      "∗"},
    {"claude", ST_WORKING,      "·"},
    {"claude", ST_RATE_LIMITED, "rate_limit_error"},
    {"claude", ST_RATE_LIMITED, "overloaded_error"},
    {"claude", ST_RATE_LIMITED, "overloaded"},
    {"claude", ST_RATE_LIMITED, "retrying in"},
    {"claude", ST_RATE_LIMITED, "429"},
    {"claude", ST_RATE_LIMITED, "529"},
    {"claude", ST_ERROR,        "api error:"},
    {"claude", ST_ERROR,        "authentication_error"},
    {"claude", ST_ERROR,        "invalid_request_error"},
    {"claude", ST_ERROR,        "\"type\":\"error\""},
    /* gemini */
    {"gemini", ST_WORKING,      "thinking ..."},
    {"gemini", ST_WORKING,      "esc to cancel"},
    {"gemini", ST_RATE_LIMITED, "quota exceeded"},
    {"gemini", ST_RATE_LIMITED, "rate limit"},
    {"gemini", ST_RATE_LIMITED, "too many requests"},
    {"gemini", ST_RATE_LIMITED, "429"},
    {"gemini", ST_IDLE,         "type your message"},
    {"gemini", ST_IDLE,         "? for shortcuts"},
    {"gemini", ST_ERROR,        "request failed after all retries"},
    {"gemini", ST_ERROR,        "error"},
    /* codex */
    {"codex",  ST_WORKING,      "working"},
    {"codex",  ST_WORKING,      "esc to interrupt"},
    {"codex",  ST_WORKING,      "thinking"},
    {"codex",  ST_WORKING,      "writing"},
    {"codex",  ST_WORKING,      "running"},
    {"codex",  ST_RATE_LIMITED, "rate limited"},
    {"codex",  ST_RATE_LIMITED, "429"},
    {"codex",  ST_IDLE,         "reply with exactly"},
    {"codex",  ST_IDLE,         "? for shortcuts"},
    {"codex",  ST_IDLE,         "context left"},
    {"codex",  ST_ERROR,        "error:"},
    /* copilot */
    {"copilot", ST_WORKING,      "thinking"},
    {"copilot", ST_WORKING,      "writing"},
    {"copilot", ST_WORKING,      "running"},
    {"copilot", ST_WORKING,      "loading environment"},
    {"copilot", ST_WORKING,      "esc to interrupt"},
    {"copilot", ST_IDLE,         "type @ to mention files"},
    {"copilot", ST_IDLE,         "type your message"},
    {"copilot", ST_RATE_LIMITED, "rate limit"},
    {"copilot", ST_RATE_LIMITED, "too many requests"},
    {"copilot", ST_RATE_LIMITED, "429"},
    {"copilot", ST_ERROR,        "error:"},
    /* vibe */
    {"vibe",   ST_WORKING,      "esc to interrupt"},
    {"vibe",   ST_RATE_LIMITED, "rate limits exceeded"},
    {"vibe",   ST_ERROR,        "error:"},
    /* qwen */
    {"qwen",   ST_IDLE,         "type your message"},
    {"qwen",   ST_IDLE,         "? for shortcuts"},
    {"qwen",   ST_RATE_LIMITED, "rate limit"},
    {"qwen",   ST_RATE_LIMITED, "429"},
    {"qwen",   ST_RATE_LIMITED, "too many requests"},
    {"qwen",   ST_ERROR,        "error:"},
    {"qwen",   ST_ERROR,        "error"},
    {NULL, 0, NULL}
};

/* Global state (protected by lock) */
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static State   g_state = ST_UNKNOWN;
static char    g_log[MAX_LOG][MAX_LINE];
static int     g_head  = 0;
static int     g_count = 0;
static char    g_agent[64] = "unknown";
static FILE   *g_state_log = NULL;
static FILE   *g_debug_log = NULL;
static struct timespec g_last_working_at = {0};
static struct timespec g_last_ingest_at = {0};
static struct timespec g_pending_idle_at = {0};
static char    g_pending_idle_line[MAX_LINE] = "";
static char    g_sock_path[256] = "";  /* for cleanup */

#define IDLE_HOLDOFF_SECS 1.0
#define QUIET_IDLE_SECS 2.0

static void cleanup_and_exit(int sig) {
    (void)sig;
    if (g_sock_path[0]) unlink(g_sock_path);
    if (g_state_log) fclose(g_state_log);
    if (g_debug_log) fclose(g_debug_log);
    _exit(0);
}

static void log_state_event(const char *event, State state, const char *line);
static void log_debug_line(const char *line);

static double monotonic_now(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec / 1000000000.0;
}

static int uses_idle_holdoff(void) {
    return strcmp(g_agent, "gemini") == 0 ||
           strcmp(g_agent, "copilot") == 0 ||
           strcmp(g_agent, "codex") == 0 ||
           strcmp(g_agent, "qwen") == 0 ||
           strcmp(g_agent, "vibe") == 0;
}

static void refresh_state_locked(void) {
    if (!uses_idle_holdoff()) return;
    if (g_state != ST_WORKING) return;
    double now = monotonic_now();
    double last = (double)g_last_working_at.tv_sec + (double)g_last_working_at.tv_nsec / 1000000000.0;
    if (g_pending_idle_at.tv_sec != 0 && g_last_working_at.tv_sec != 0 && now - last >= IDLE_HOLDOFF_SECS) {
        g_state = ST_IDLE;
        log_state_event("change", g_state, g_pending_idle_line[0] ? g_pending_idle_line : NULL);
        g_pending_idle_at.tv_sec = 0;
        g_pending_idle_at.tv_nsec = 0;
        g_pending_idle_line[0] = '\0';
        return;
    }
    if (g_last_ingest_at.tv_sec == 0 || g_last_working_at.tv_sec == 0) return;
    double last_ingest = (double)g_last_ingest_at.tv_sec + (double)g_last_ingest_at.tv_nsec / 1000000000.0;
    if (now - last < IDLE_HOLDOFF_SECS) return;
    if (now - last_ingest < QUIET_IDLE_SECS) return;
    g_state = ST_IDLE;
    log_state_event("change", g_state, NULL);
}

static void *tick_thread(void *arg) {
    (void)arg;
    while (1) {
        pthread_mutex_lock(&lock);
        refresh_state_locked();
        pthread_mutex_unlock(&lock);
        usleep(100000);
    }
    return NULL;
}

static void json_write_escaped(FILE *out, const char *s) {
    for (int i = 0; s[i]; i++) {
        unsigned char c = (unsigned char)s[i];
        if (c == '"' || c == '\\') fputc('\\', out);
        if (c >= 0x20) fputc(c, out);
    }
}

static void log_state_event(const char *event, State state, const char *line) {
    if (!g_state_log) return;
    time_t now = time(NULL);
    struct tm tm;
    gmtime_r(&now, &tm);
    char ts[32];
    strftime(ts, sizeof(ts), "%Y-%m-%dT%H:%M:%SZ", &tm);
    fprintf(g_state_log,
            "{\"ts\":\"%s\",\"event\":\"%s\",\"agent\":\"%s\",\"state\":\"%s\"",
            ts, event, g_agent, STATE_STR[state]);
    if (line) {
        fputs(",\"line\":\"", g_state_log);
        json_write_escaped(g_state_log, line);
        fputc('"', g_state_log);
    }
    fputs("}\n", g_state_log);
    fflush(g_state_log);
}

static void log_debug_line(const char *line) {
    if (!g_debug_log) return;
    fputc('\'', g_debug_log);
    for (int i = 0; line[i]; i++) {
        unsigned char c = (unsigned char)line[i];
        if (c == '\\' || c == '\'') {
            fputc('\\', g_debug_log);
            fputc(c, g_debug_log);
        } else if (c == '\n') {
            fputs("\\n", g_debug_log);
        } else if (c == '\r') {
            fputs("\\r", g_debug_log);
        } else if (c == '\t') {
            fputs("\\t", g_debug_log);
        } else if (c < 0x20 || c == 0x7f) {
            fprintf(g_debug_log, "\\x%02x", c);
        } else {
            fputc(c, g_debug_log);
        }
    }
    fputs("'\n", g_debug_log);
    fflush(g_debug_log);
}

/* Case-insensitive substring search */
static int icontains(const char *hay, const char *needle) {
    size_t nlen = strlen(needle), hlen = strlen(hay);
    if (nlen > hlen) return 0;
    for (size_t i = 0; i <= hlen - nlen; i++) {
        size_t j;
        for (j = 0; j < nlen; j++)
            if (tolower((unsigned char)hay[i+j]) != tolower((unsigned char)needle[j])) break;
        if (j == nlen) return 1;
    }
    return 0;
}

/* Strip ANSI escape sequences in-place */
static void strip_ansi(char *s) {
    char *r = s, *w = s;
    while (*r) {
        if (*r == '\x1b') {
            r++;
            if (*r == '[') {
                /* CSI sequence: ESC [ params final-byte */
                r++;
                while (*r && !(*r >= '@' && *r <= '~')) r++;
                if (*r) r++;
            } else if (*r == ']') {
                /* OSC sequence: ESC ] text ST (BEL or ESC \) */
                r++;
                while (*r && *r != '\x07' && *r != '\x1b') r++;
                if (*r == '\x07') r++;
                else if (*r == '\x1b' && *(r+1) == '\\') r += 2;
            } else if (*r >= '@' && *r <= '_') {
                /* Fe sequence: single char after ESC */
                r++;
            } else if (*r == '\\') {
                /* String terminator (after ST) */
                r++;
            }
        } else if (*r == '[') {
            /* Orphaned CSI (no ESC) - skip if it looks like CSI sequence */
            char *peek = r + 1;
            while (*peek && !(*peek >= '@' && *peek <= '~')) peek++;
            if (*peek >= '@' && *peek <= '~') {
                r = peek + 1;  /* Skip the whole sequence */
            } else {
                *w++ = *r++;
            }
        } else {
            *w++ = *r++;
        }
    }
    *w = '\0';
}

/* Braille block U+2800-U+28FF encodes as E2 A0 xx in UTF-8 (xx is 0x80-0xBF) */
static int has_braille(const char *line) {
    for (int i = 0; line[i] && line[i+1] && line[i+2]; i++) {
        unsigned char c0 = (unsigned char)line[i];
        unsigned char c1 = (unsigned char)line[i+1];
        unsigned char c2 = (unsigned char)line[i+2];
        if (c0 == 0xE2 && c1 == 0xA0 && c2 >= 0x80 && c2 <= 0xBF)
            return 1;
    }
    return 0;
}

static void trim_ascii_ws(char *s) {
    int i = 0, j = 0, len = (int)strlen(s);
    while (s[i] && isspace((unsigned char)s[i])) i++;
    if (i > 0) {
        while (s[i]) s[j++] = s[i++];
        s[j] = '\0';
    }
    len = (int)strlen(s);
    while (len > 0 && isspace((unsigned char)s[len - 1])) s[--len] = '\0';
}

static int has_claude_working_marker(const char *line) {
    return has_braille(line) ||
           icontains(line, "esc to cancel") ||
           strstr(line, "·") || strstr(line, "✢") || strstr(line, "✳") ||
           strstr(line, "∗") || strstr(line, "✻") || strstr(line, "✽");
}

static int prompt_suffix_only(const char *s) {
    while (*s) {
        if (*s == ' ') {
            s++;
            continue;
        }
        if ((unsigned char)s[0] == 0xC2 && (unsigned char)s[1] == 0xA0) {
            s += 2;
            continue;
        }
        return 0;
    }
    return 1;
}

static int is_claude_idle(const char *line) {
    if (line[0] == '>' && line[1] == '\0') return 1;
    const char *prompt = NULL;
    for (const char *p = line; (p = strstr(p, "❯")); p += 3) prompt = p;
    if (!prompt) return 0;
    if (prompt == line && prompt_suffix_only(prompt + 3)) return 1;
    if (prompt_suffix_only(prompt + 3) && !has_claude_working_marker(line)) return 1;
    return 0;
}

static int is_claude_insert_redraw(const char *line) {
    return strncmp(line, "--INSERT--", 10) == 0;
}

static int is_copilot_idle(const char *line) {
    if (line[0] == '>' && line[1] == '\0') return 1;
    if ((unsigned char)line[0] == 0xE2 &&
        (unsigned char)line[1] == 0x80 &&
        (unsigned char)line[2] == 0xBA &&
        line[3] == '\0') return 1; /* › */
    return 0;
}

static int is_vibe_logo_line(const char *line) {
    return icontains(line, "Mistral Vibe") ||
           (icontains(line, "models") && icontains(line, "MCP server")) ||
           icontains(line, "skills");
}

static int is_vibe_idle(const char *line) {
    if (line[0] == '>' && line[1] == '\0') return 1;
    return strstr(line, "│ >") != NULL;
}

static State classify(char *line) {
    int has_sync = strstr(line, "\x1b[?2026") != NULL;
    /* Skip title bar updates - they contain spinners but aren't real work */
    if (strstr(line, "\x1b]") && strstr(line, "Claude Code")) return ST_UNKNOWN;
    strip_ansi(line);
    trim_ascii_ws(line);
    if (!strcmp(g_agent, "claude") && is_claude_insert_redraw(line)) return ST_UNKNOWN;
    if (!strcmp(g_agent, "claude") && is_claude_idle(line)) return ST_IDLE;
    if (!strcmp(g_agent, "claude") && has_claude_working_marker(line)) return ST_WORKING;
    if (!strcmp(g_agent, "copilot") && is_copilot_idle(line)) return ST_IDLE;
    if (!strcmp(g_agent, "vibe") && is_vibe_idle(line)) return ST_IDLE;
    if ((!strcmp(g_agent, "gemini") || !strcmp(g_agent, "qwen")) && has_braille(line)) return ST_WORKING;
    if (!strcmp(g_agent, "vibe") && icontains(line, "esc to interrupt")) return ST_WORKING;
    if (!strcmp(g_agent, "vibe") && has_braille(line) && !is_vibe_logo_line(line) && icontains(line, "analyse")) return ST_WORKING;
    if (!strcmp(g_agent, "claude") && has_sync) return ST_WORKING;
    for (int i = 0; PATS[i].agent; i++)
        if (!strcmp(PATS[i].agent, g_agent) && icontains(line, PATS[i].pat))
            return PATS[i].state;
    return ST_UNKNOWN;  /* no match — caller keeps existing state */
}

static void ingest(const char *line) {
    pthread_mutex_lock(&lock);
    log_debug_line(line);
    clock_gettime(CLOCK_MONOTONIC, &g_last_ingest_at);
    strncpy(g_log[g_head], line, MAX_LINE - 1);
    g_log[g_head][MAX_LINE - 1] = '\0';
    g_head = (g_head + 1) % MAX_LOG;
    if (g_count < MAX_LOG) g_count++;
    refresh_state_locked();
    State s = classify((char *)line);
    if (s == ST_WORKING) {
        clock_gettime(CLOCK_MONOTONIC, &g_last_working_at);
        g_pending_idle_at.tv_sec = 0;
        g_pending_idle_at.tv_nsec = 0;
        g_pending_idle_line[0] = '\0';
    } else if (uses_idle_holdoff() && s == ST_IDLE && g_last_working_at.tv_sec != 0) {
        double last = (double)g_last_working_at.tv_sec + (double)g_last_working_at.tv_nsec / 1000000000.0;
        if (monotonic_now() - last < IDLE_HOLDOFF_SECS) {
            clock_gettime(CLOCK_MONOTONIC, &g_pending_idle_at);
            strncpy(g_pending_idle_line, line, MAX_LINE - 1);
            g_pending_idle_line[MAX_LINE - 1] = '\0';
            s = ST_UNKNOWN;
        }
    }
    if (s != ST_UNKNOWN && s != g_state) {
        g_state = s;
        log_state_event("change", g_state, line);
    }
    pthread_mutex_unlock(&lock);
}

/* Write a JSON-escaped string into buf, return bytes written */
static int json_str(char *buf, int cap, const char *s) {
    int n = 0;
    buf[n++] = '"';
    for (int i = 0; s[i] && n < cap - 6; i++) {
        unsigned char c = s[i];
        if (c == '"')       { buf[n++] = '\\'; buf[n++] = '"'; }
        else if (c == '\\') { buf[n++] = '\\'; buf[n++] = '\\'; }
        else if (c == '\n') { buf[n++] = '\\'; buf[n++] = 'n'; }
        else if (c == '\r') { buf[n++] = '\\'; buf[n++] = 'r'; }
        else if (c == '\t') { buf[n++] = '\\'; buf[n++] = 't'; }
        else if (c < 0x20)  { /* escape as \u00XX */
            buf[n++] = '\\'; buf[n++] = 'u'; buf[n++] = '0'; buf[n++] = '0';
            buf[n++] = "0123456789abcdef"[c >> 4];
            buf[n++] = "0123456789abcdef"[c & 0xF];
        }
        else                  buf[n++] = c;
    }
    buf[n++] = '"';
    buf[n]   = '\0';
    return n;
}

/* Fill out with JSON response for cmd, return length (no trailing newline) */
static int handle_query(const char *cmd, char *out, int cap) {
    pthread_mutex_lock(&lock);
    int n = 0;

    if (!strncmp(cmd, "status", 6)) {
        n = snprintf(out, cap, "{\"state\":\"%s\"}", STATE_STR[g_state]);

    } else if (!strncmp(cmd, "tail", 4)) {
        if (g_count == 0) {
            n = snprintf(out, cap, "{\"line\":null}");
        } else {
            int idx = (g_head - 1 + MAX_LOG) % MAX_LOG;
            char esc[MAX_LINE * 2];
            json_str(esc, sizeof(esc), g_log[idx]);
            n = snprintf(out, cap, "{\"line\":%s}", esc);
        }

    } else if (!strncmp(cmd, "log", 3)) {
        int tail  = g_count < 50 ? g_count : 50;
        int start = (g_head - tail + MAX_LOG) % MAX_LOG;
        n += snprintf(out + n, cap - n, "{\"log\":[");
        for (int i = 0; i < tail; i++) {
            char esc[MAX_LINE * 2];
            json_str(esc, sizeof(esc), g_log[(start + i) % MAX_LOG]);
            n += snprintf(out + n, cap - n, "%s%s", esc, i < tail - 1 ? "," : "");
        }
        n += snprintf(out + n, cap - n, "]}");

    } else {
        n = snprintf(out, cap, "{\"error\":\"unknown command\"}");
    }

    pthread_mutex_unlock(&lock);
    return n;
}

/* Unix socket server */
static void *sock_thread(void *arg) {
    const char *path = (const char *)arg;
    int srv = socket(AF_UNIX, SOCK_STREAM, 0);
    struct sockaddr_un addr = {0};
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, path, sizeof(addr.sun_path) - 1);
    unlink(path);
    bind(srv, (struct sockaddr *)&addr, sizeof(addr));
    listen(srv, 5);
    while (1) {
        int conn = accept(srv, NULL, NULL);
        if (conn < 0) continue;
        char buf[256] = {0};
        (void)read(conn, buf, sizeof(buf) - 1);
        /* trim whitespace */
        int len = strlen(buf);
        while (len > 0 && (buf[len-1] == '\n' || buf[len-1] == '\r' || buf[len-1] == ' '))
            buf[--len] = '\0';
        static char resp[RESP_MAX];
        int rlen = handle_query(buf, resp, RESP_MAX);
        resp[rlen++] = '\n';
        (void)write(conn, resp, rlen);
        close(conn);
    }
    return NULL;
}

/* Minimal HTTP server */
static void *http_thread(void *arg) {
    int port = *(int *)arg;
    int srv = socket(AF_INET, SOCK_STREAM, 0);
    int opt = 1;
    setsockopt(srv, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
    struct sockaddr_in addr = {0};
    addr.sin_family      = AF_INET;
    addr.sin_port        = htons(port);
    addr.sin_addr.s_addr = INADDR_ANY;
    bind(srv, (struct sockaddr *)&addr, sizeof(addr));
    listen(srv, 5);
    while (1) {
        int conn = accept(srv, NULL, NULL);
        if (conn < 0) continue;
        char req[512] = {0};
        (void)read(conn, req, sizeof(req) - 1);
        /* parse: GET /path HTTP/1.x */
        char method[8], raw[64], proto[16];
        raw[0] = '\0';
        sscanf(req, "%7s %63s %15s", method, raw, proto);
        /* strip leading / */
        char *path = raw[0] == '/' ? raw + 1 : raw;
        if (*path == '\0') path = "status";
        static char body[RESP_MAX];
        int blen = handle_query(path, body, RESP_MAX);
        char hdr[128];
        int hlen = snprintf(hdr, sizeof(hdr),
            "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n", blen);
        (void)write(conn, hdr, hlen);
        (void)write(conn, body, blen);
        close(conn);
    }
    return NULL;
}

int main(int argc, char **argv) {
    char sock_path[256] = "";
    int  http_port      = 0;
    char state_log_path[256] = "";
    char debug_path[256] = "";

    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--agent")     && i+1 < argc) strncpy(g_agent,   argv[++i], sizeof(g_agent)   - 1);
        if (!strcmp(argv[i], "--socket")    && i+1 < argc) strncpy(sock_path, argv[++i], sizeof(sock_path) - 1);
        if (!strcmp(argv[i], "--http-port") && i+1 < argc) http_port = atoi(argv[++i]);
        if (!strcmp(argv[i], "--debug")     && i+1 < argc) strncpy(debug_path, argv[++i], sizeof(debug_path) - 1);
        if (!strcmp(argv[i], "--state-log") && i+1 < argc) strncpy(state_log_path, argv[++i], sizeof(state_log_path) - 1);
        if (!strcmp(argv[i], "--help")) {
            printf("Usage: monitor --agent <name> --socket <path> [--http-port <port>] [--debug <path>] [--state-log <path>]\n");
            return 0;
        }
    }

    signal(SIGPIPE, SIG_IGN);
    signal(SIGINT, cleanup_and_exit);
    signal(SIGTERM, cleanup_and_exit);

    /* store socket path for cleanup */
    if (sock_path[0]) strncpy(g_sock_path, sock_path, sizeof(g_sock_path) - 1);

    if (state_log_path[0]) {
        g_state_log = fopen(state_log_path, "w");
        if (!g_state_log) {
            perror("fopen state-log");
            return 1;
        }
        log_state_event("init", g_state, NULL);
    }

    if (debug_path[0]) {
        g_debug_log = fopen(debug_path, "w");
        if (!g_debug_log) {
            perror("fopen debug");
            return 1;
        }
    }

    pthread_t t;
    if (sock_path[0])
        pthread_create(&t, NULL, sock_thread, sock_path);
    if (http_port) {
        static int port;
        port = http_port;
        pthread_create(&t, NULL, http_thread, &port);
    }
    pthread_create(&t, NULL, tick_thread, NULL);

    char line[MAX_LINE];
    while (fgets(line, sizeof(line), stdin)) {
        int len = strlen(line);
        while (len > 0 && (line[len-1] == '\n' || line[len-1] == '\r'))
            line[--len] = '\0';
        ingest(line);
    }
    return 0;
}
