# Free and low-cost models (aider)

`agent: aider` runs any litellm-backed model in a swarm pane. Aliases live in `swarm/models.yaml` (`aider:*`).

## Keys

- `~/.cred/ai.sh` holds `export GEMINI_API_KEY=…`, `GROQ_API_KEY`, `MISTRAL_API_KEY`, `OPENROUTER_API_KEY`.
- Aliases pass `--env-file ~/.cred/ai.sh`. Never put keys in swarm YAML.
- Flags: `--yes-always` (no prompts), `--no-auto-commits` (the agent commits, per repo rules), `--no-gitignore` (skips a blocking .gitignore prompt; `.aider*` is ignored in this repo).

## Aliases

| alias | model | free tier |
|---|---|---|
| `aider:gemini` | gemini/gemini-3.8-flash | Google AI Studio |
| `aider:gemini-pro` | gemini/gemini-3.1-pro-preview | Google AI Studio (preview) |
| `aider:groq` | qwen3.8-27b | Groq |
| `aider:groq-oss` | gpt-oss-120b | Groq |
| `aider:codestral` | codestral-latest | Mistral |
| `aider:mistral-code` | mistral-code-latest | Mistral |
| `aider:cohere` | cohere/north-mini-code:free | OpenRouter `:free` |
| `aider:nemotron` | nemotron-3-ultra-550b-a55b:free | OpenRouter `:free` |

Groq ids verified with `aider --list-models`; the others are from TASK-89 or review and not all verified. Check with `aider --list-models <name>`.

## Free ceilings and paid upgrade

- Limits and prices differ per model and change. Check the provider console before relying on them.
- Google: gemini-3.8-flash is ~$0.75/1M input on pay-as-you-go (reviewer-checked; the older ~$0.075 figure in TASK-89 is wrong for 3.8). Enable billing on the AI Studio project to lift free limits.
- Groq: qwen/qwen3.8-27b is ~$0.80/1M input, $4/1M output, and the free tier is ~1K req/day for it (not 14.4k, which applies to smaller models). Upgrade via the Developer tier in Groq Console.
- Hitting a limit: swap the pane's alias or enable billing. Only the key/alias changes.

## Gotchas

- Aider only sees git-tracked files plus files you `/add`. In a new repo with no commits it cannot see anything: `git add -A && git commit -m init` first, then start the swarm.
- Run `make install-aiswarm` first if `aiswarm init --flavour free` is rejected (stale installed copy).

## Found in live use

- gemini-2.5-pro: 404 for new accounts, replaced by gemini-3.1-pro-preview.
- nemotron-3-super-120b-a12b:free: listed by OpenRouter but its Nvidia backend 404s. Use nemotron-3-ultra-550b-a55b:free.
- Groq free tier TPM is tiny (qwen ~7k input tokens/min, gpt-oss ~8k). Aider's repo-map blows it, so Groq aliases use `--map-tokens 0`. Expect rate limits on large files even so.
- gemini-3.8-flash can return 503 "high demand". Aider retries.

## Monitor

- `aider` uses the generic rule: any output is `working`, quiet timeout is `idle`. No aider-specific UI patterns.
- Quota: `AGENT_STATS_CMD` is `None`. No quota probing or EMA pacing. Babysit uses fixed `interval_secs`.
- Aider does not self-resume. `aiswarm` session-id tracking is not wired for it.

## Try it

In a test project: `aiswarm init --flavour free` (8 aider panes, one per alias). Or the 2-pane `swarm/templates/free-tier.yaml`:

    aiswarm start swarm/templates/free-tier.yaml
