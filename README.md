# OpenRouter Fallback Rotator for Hermes

A deterministic, script-only Hermes cron job that refreshes only the fallback provider chain from OpenRouter free models.

Unlike the original primary-model rotator, this variant preserves your existing main model/provider and only refreshes the secondary models Hermes will try if the primary fails.

## What’s included

- `scripts/openrouter_fallback_check.py` — the executable cron script
- `scripts/pin_cron_to_first_fallback.py` — optional helper that can repin selected cron jobs to the new top fallback when explicitly enabled
- `openrouter_tiers.example.json` — example tier list for capability-based scoring
- `skills/openrouter-fallback-rotator/SKILL.md` — the Hermes skill doc for discoverability
- `install.sh` — local installer for Hermes users
- `tests/test_openrouter_fallback_check.py` — regression tests for the rotator
- `CHANGELOG.md` — reverse-chronological project change history

## Current behavior

The rotator:

- fetches OpenRouter models from `/api/v1/models`
- keeps only `:free` models with sane metadata and zero pricing
- reads an optional tier list from `~/.hermes/openrouter_tiers.json`
- drops models below the configured minimum tier score or context length
- probes candidates with a minimal chat completion
- ranks eligible models by:
  - unthrottled before throttled
  - higher tier score first
  - larger context window first
  - newer `created` first
  - model id as a final stable tie-break
- writes the top N free models into `fallback_providers`
- preserves `model.provider`, `model.default`, and `model.base_url`
- fails closed and leaves config untouched if validation fails
- stores the previous selection in a state file for diffing
- leaves cron-job model pins alone unless you explicitly enable repinning with `OPENROUTER_SYNC_CRON_PINS=1`

The helper script is installed for users who want that behavior, but automatic cron repinning is disabled by default.

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

That copies the script, helper, skill, and example tier file into your Hermes home and prints the exact setup steps.

## Full setup after install

1. Add your OpenRouter API key:

```bash
hermes config set OPENROUTER_API_KEY sk-or-...
```

2. Optionally customize the tier list:

```bash
cp ~/.hermes/openrouter_tiers.example.json ~/.hermes/openrouter_tiers.json
```

3. Register the refresh cron:

```bash
hermes cron create '0 7 * * *' \
  --name openrouter-fallback-rotator \
  --script openrouter_fallback_check.py \
  --no-agent \
  --deliver telegram
```

4. Prime `fallback_providers` immediately instead of waiting for the first scheduled run:

```bash
python3 ~/.hermes/scripts/openrouter_fallback_check.py
```

5. Verify your main model was preserved and fallbacks were populated:

```bash
hermes config get model
hermes config get fallback_providers
```

Adjust `--deliver` for your preferred Hermes gateway target.

## Optional environment knobs

```bash
export OPENROUTER_FALLBACK_CHAIN_LENGTH=3
export HERMES_TIER_CONFIG_PATH=~/.hermes/openrouter_tiers.json
export OPENROUTER_SYNC_CRON_PINS=1   # optional; default is disabled
```

## What automatic fallback looks like

After setup, Hermes continues using your existing primary model. If that provider fails with a fallback-triggering error, Hermes will try the OpenRouter free models currently listed in `fallback_providers`.

## Filesystem layout

```text
openrouter-fallback-rotator/
├── README.md
├── LICENSE
├── install.sh
├── openrouter_tiers.example.json
├── scripts/
│   ├── openrouter_fallback_check.py
│   └── pin_cron_to_first_fallback.py
├── skills/
│   └── openrouter-fallback-rotator/
│       └── SKILL.md
└── tests/
    └── test_openrouter_fallback_check.py
```
