/*
 * monitor.c — track pane activity from stdin, serve state over Unix socket + HTTP.
 *
 * Usage:
 *   ./monitor --agent claude --socket /tmp/mysession.sock [--idle-secs 10]
 *   echo status | nc -U /tmp/mysession.sock
 *   curl localhost:9000/status
 *
 * Compile: cc -O2 -o monitor monitor.c -lpthread
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <math.h>
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
typedef enum { ST_UNKNOWN, ST_WORKING, ST_IDLE } State;
static const char *STATE_STR[] = { "unknown", "working", "idle" };

static const char *VALID_AGENTS_TEXT = "claude, codex, copilot, gemini, grok, vibe, qwen, antigravity";
static const char *VALID_AGENTS[] = {
    "claude", "codex", "copilot", "gemini", "grok", "vibe", "qwen", "antigravity", NULL
};

static int valid_agent(const char *agent) {
    for (int i = 0; VALID_AGENTS[i]; i++)
        if (!strcmp(VALID_AGENTS[i], agent)) return 1;
    return 0;
}

static int parse_positive_double(const char *value, double *out) {
    char *end;
    errno = 0;
    double parsed = strtod(value, &end);
    if (errno || end == value || *end || !isfinite(parsed) || parsed <= 0) return 0;
    *out = parsed;
    return 1;
}

/* Global state (protected by lock) */
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static State   g_state = ST_UNKNOWN;
static char    g_log[MAX_LOG][MAX_LINE];
static int     g_head  = 0;
static int     g_count = 0;
static char    g_agent[64] = "unknown";
static FILE   *g_state_log = NULL;
static FILE   *g_debug_log = NULL;
static struct timespec g_last_ingest_at = {0};
static char    g_sock_path[256] = "";  /* for cleanup */
static double  g_idle_secs = 10.0;

static void cleanup_and_exit(int sig) {
    (void)sig;
    if (g_sock_path[0]) unlink(g_sock_path);
    if (g_state_log) fclose(g_state_log);
    if (g_debug_log) fclose(g_debug_log);
    _exit(0);
}

static void cleanup_resources(void) {
    if (g_sock_path[0]) unlink(g_sock_path);
    if (g_state_log) fclose(g_state_log);
    if (g_debug_log) fclose(g_debug_log);
}

static void log_state_event(const char *event, State state, const char *line);
static void log_debug_line(const char *line);

static double monotonic_now(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec / 1000000000.0;
}

static void refresh_state_locked(void) {
    if (!strcmp(g_agent, "grok")) return;
    if (g_state != ST_WORKING) return;
    if (g_last_ingest_at.tv_sec == 0) return;
    double last_ingest = (double)g_last_ingest_at.tv_sec + (double)g_last_ingest_at.tv_nsec / 1000000000.0;
    if (monotonic_now() - last_ingest < g_idle_secs) return;
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

static int parse_terminal_title(const char *line, char *title, int max_len) {
    const char *p = line;
    while (*p) {
        if (p[0] == '\x1b' && p[1] == ']' && (p[2] == '0' || p[2] == '2') && p[3] == ';') {
            p += 4;
            int len = 0;
            while (*p && *p != '\x07' && len < max_len - 1) {
                if (p[0] == '\x1b' && p[1] == '\\') {
                    break;
                }
                title[len++] = *p++;
            }
            title[len] = '\0';
            return 1;
        }
        p++;
    }
    return 0;
}

static void ingest(const char *line) {
    pthread_mutex_lock(&lock);
    log_debug_line(line);
    clock_gettime(CLOCK_MONOTONIC, &g_last_ingest_at);
    strncpy(g_log[g_head], line, MAX_LINE - 1);
    g_log[g_head][MAX_LINE - 1] = '\0';
    g_head = (g_head + 1) % MAX_LOG;
    if (g_count < MAX_LOG) g_count++;

    char title[256];
    if (parse_terminal_title(line, title, sizeof(title))) {
        if (!strcmp(g_agent, "grok")) {
            State new_state = g_state;
            if (strcmp(title, "grok") == 0) {
                new_state = ST_IDLE;
            } else {
                new_state = ST_WORKING;
            }
            if (g_state != new_state) {
                g_state = new_state;
                log_state_event("change", g_state, line);
            }
            pthread_mutex_unlock(&lock);
            return;
        }
    }

    if (!strcmp(g_agent, "grok")) {
        if (g_state == ST_UNKNOWN) {
            g_state = ST_WORKING;
            log_state_event("change", g_state, line);
        }
        pthread_mutex_unlock(&lock);
        return;
    }

    if (g_state != ST_WORKING) {
        g_state = ST_WORKING;
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
    int srv = socket(AF_INET6, SOCK_STREAM, 0);
    int opt = 1;
    setsockopt(srv, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
    struct sockaddr_in6 addr = {0};
    addr.sin6_family = AF_INET6;
    addr.sin6_port = htons(port);
    addr.sin6_addr = in6addr_any;
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
        if (!strcmp(argv[i], "--idle-secs") && i+1 < argc) {
            if (!parse_positive_double(argv[++i], &g_idle_secs)) {
                fprintf(stderr, "--idle-secs must be a positive number\n");
                return 2;
            }
        }
        if (!strcmp(argv[i], "--debug")     && i+1 < argc) strncpy(debug_path, argv[++i], sizeof(debug_path) - 1);
        if (!strcmp(argv[i], "--state-log") && i+1 < argc) strncpy(state_log_path, argv[++i], sizeof(state_log_path) - 1);
        if (!strcmp(argv[i], "--help")) {
            printf("Usage: monitor --agent <name> --socket <path> [--http-port <port>] [--idle-secs <seconds>] [--debug <path>] [--state-log <path>]\n");
            printf("Valid agent types: %s\n", VALID_AGENTS_TEXT);
            return 0;
        }
    }

    if (!valid_agent(g_agent)) {
        fprintf(stderr, "unknown agent type: %s. Valid agent types: %s\n", g_agent, VALID_AGENTS_TEXT);
        return 2;
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
    cleanup_resources();
    return 0;
}
