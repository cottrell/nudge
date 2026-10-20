# Free and low-cost models (aider)

`agent: aider` runs any litellm-backed model in a swarm pane. Aliases live in `swarm/models.yaml` (`aider:*`).

## Keys

- `~/.cred/ai.sh` holds `export GEMINI_API_KEY=…`, `GROQ_API_KEY`, `MISTRAL_API_KEY`, `OPENROUTER_API_KEY`.
- Aliases pass `--env-file ~/.cred/ai.sh`. Never put keys in swarm YAML.
- Flags: `--yes-always` (no prompts), `--no-auto-commits` (the agent commits, per repo rules), `--no-gitignore` (skips a blocking .gitignore prompt; `.aider*` is ignored in this repo).

## Aliases

| alias | model | free tier |
|---|---|---|
| `aider:gemini` | gemini-3.8-flash | Google AI Studio |
| `aider:gemini-pro` | gemini-2.5-pro | Google AI Studio (tighter) |
| `aider:groq` | qwen3.8-27b | Groq |
| `aider:groq-oss` | gpt-oss-120b | Groq |
| `aider:codestral` | codestral-latest | Mistral |
| `aider:mistral-code` | mistral-code-latest | Mistral |
| `aider:cohere` | cohere/north-mini-code:free | OpenRouter `:free` |
| `aider:nemotron` | nemotron-3-super-120b:free | OpenRouter `:free` |

Model ids are from TASK-89 and not verified against live provider lists. Check with `aider --list-models <name>`.

## Free ceilings and paid upgrade

- Google: ~1.5k req/day, 1M TPM free. Pay-as-you-go: enable billing on the AI Studio project; Flash ~$0.075/1M input tokens.
- Groq: ~14.4k req/day, 30 RPM free. Pay-as-you-go: Developer tier in Groq Console; ~$0.20/1M tokens on small models.
- Prices and limits are approximate (TASK-89 figures). Confirm in the provider console before relying on them.
- Hitting a limit: swap the pane's alias or enable billing. No config other than the key changes.

## Monitor

- `aider` uses the generic rule: any output is `working`, quiet timeout is `idle`. No aider-specific UI patterns.
- Quota: `AGENT_STATS_CMD` is `None`. No quota probing or EMA pacing. Babysit uses fixed `interval_secs`.
- Aider does not self-resume. `aiswarm` session-id tracking is not wired for it.

## Try it

`aiswarm init` is not changed. Use `swarm/templates/free-tier.yaml`:

    aiswarm start swarm/templates/free-tier.yaml
