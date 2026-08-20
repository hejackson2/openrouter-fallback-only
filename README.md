# OpenRouter Fallback Rotator for Hermes

A deterministic, script-only Hermes cron job that scans OpenRouter free models, probes them, and updates only the Hermes fallback provider chain.

Unlike the original primary-model rotator, this variant preserves your existing main model/provider and only refreshes the secondary models Hermes will try if the primary fails.

## What’s included

- `scripts/openrouter_fallback_check.py` — the executable cron script
- `skills/openrouter-fallback-rotator/SKILL.md` — the Hermes skill doc for discoverability
- `install.sh` — local installer for Hermes users

## Behavior

- Fetches OpenRouter models from `/api/v1/models`
- Keeps only `:free` models with sane metadata
- Probes candidates with a minimal chat completion
- Ranks healthy models by unthrottled status, then context window, then recency
- Writes the top N free models into `fallback_providers`
- Preserves `model.provider`, `model.default`, and `model.base_url`
- Fails closed and leaves config untouched if validation fails

## Prerequisites

Each user needs their own:

- `OPENROUTER_API_KEY` in `~/.hermes/.env`
- Hermes installation
- permissions to run cron jobs on their profile

## Install into your own Hermes

From the repo root:

```bash
bash install.sh
```

That copies the skill and script into your Hermes home and prints the exact setup steps.

## Full setup after install

To make Hermes automatically fall back to the best free OpenRouter models when your primary model fails or hits quota/rate limits:

1. Add your OpenRouter API key:

```bash
hermes config set OPENROUTER_API_KEY sk-or-...
```

2. Register the refresh cron:

```bash
hermes cron create '0 7 * * *' \
  --name openrouter-fallback-rotator \
  --script openrouter_fallback_check.py \
  --no-agent \
  --deliver telegram
```

3. Prime `fallback_providers` immediately instead of waiting for the first scheduled run:

```bash
python3 ~/.hermes/scripts/openrouter_fallback_check.py
```

4. Verify your main model was preserved and fallbacks were populated:

```bash
hermes config get model
hermes config get fallback_providers
```

Adjust `--deliver` for your preferred Hermes gateway target.

## What automatic fallback looks like

After setup, Hermes continues using your existing primary model. If that provider fails with a fallback-triggering error (for example quota exhaustion or rate limiting), Hermes will try the OpenRouter free models currently listed in `fallback_providers`.

## Optional chain length

By default the script writes 3 fallback models. To change that, set:

```bash
export OPENROUTER_FALLBACK_CHAIN_LENGTH=5
```

## Filesystem layout

```text
openrouter-fallback-rotator/
├── README.md
├── LICENSE
├── install.sh
├── scripts/
│   └── openrouter_fallback_check.py
└── skills/
    └── openrouter-fallback-rotator/
        └── SKILL.md
```
