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
| `aider:gemini-pro` | gemini/gemini-2.5-pro | Google AI Studio (tighter) |
| `aider:groq` | qwen3.8-27b | Groq |
| `aider:groq-oss` | gpt-oss-120b | Groq |
| `aider:codestral` | codestral-latest | Mistral |
| `aider:mistral-code` | mistral-code-latest | Mistral |
| `aider:cohere` | cohere/north-mini-code:free | OpenRouter `:free` |
| `aider:nemotron` | nemotron-3-super-120b:free | OpenRouter `:free` |

Groq ids verified with `aider --list-models`; the others are from TASK-89 or review and not all verified. Check with `aider --list-models <name>`.

## Free ceilings and paid upgrade

- Limits and prices differ per model and change. Check the provider console before relying on them.
- Google: gemini-3.8-flash is ~$0.75/1M input on pay-as-you-go (reviewer-checked; the older ~$0.075 figure in TASK-89 is wrong for 3.8). Enable billing on the AI Studio project to lift free limits.
- Groq: qwen/qwen3.8-27b is ~$0.80/1M input, $4/1M output, and the free tier is ~1K req/day for it (not 14.4k, which applies to smaller models). Upgrade via the Developer tier in Groq Console.
- Hitting a limit: swap the pane's alias or enable billing. Only the key/alias changes.

## Monitor

- `aider` uses the generic rule: any output is `working`, quiet timeout is `idle`. No aider-specific UI patterns.
- Quota: `AGENT_STATS_CMD` is `None`. No quota probing or EMA pacing. Babysit uses fixed `interval_secs`.
- Aider does not self-resume. `aiswarm` session-id tracking is not wired for it.

## Try it

`aiswarm init` is not changed. Use `swarm/templates/free-tier.yaml`:

    aiswarm start swarm/templates/free-tier.yaml
