---
name: openrouter-fallback-rotator
description: "Use when building the OpenRouter free-model fallback rotator."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [hermes, cron, openrouter, config, automation, fallback]
---

# OpenRouter Fallback Rotator

Use this skill when you need to build, inspect, or rerun the deterministic Hermes cron that selects the best healthy OpenRouter free models and writes them into Hermes fallback config.

## What it does

- Fetches OpenRouter `/models` with `OPENROUTER_API_KEY`
- Filters `:free` models with sane metadata
- Probes candidates with a minimal chat completion
- Ranks healthy models by:
  1. unthrottled before throttled
  2. `context_length` descending
  3. newer `created` first
- Writes the top N models into `fallback_providers`
- Preserves the current primary model under `model.*`
- Stores the previous fallback selection in `~/.hermes/state/openrouter_fallback_rotator.json`
- Backs up config to `~/.hermes/config.yaml.bak` before a successful update

## Safety invariants

- Fail closed on any validation error
- No LLM at execution time
- Idempotent: repeated runs with the same selection do not rewrite config
- Atomic writes only
- No partial config updates
- Primary model/provider are never rewritten

## Files

- Script: `~/.hermes/scripts/openrouter_fallback_check.py`
- State: `~/.hermes/state/openrouter_fallback_rotator.json`
- Backup: `~/.hermes/config.yaml.bak`

## Cron shape

- Schedule: `0 7 * * *`
- Mode: `no_agent=True`
- Deliver: home channel / gateway target when available
- Name: `openrouter-fallback-rotator`

## Setup checklist

1. Install with `bash install.sh`.
2. Add `OPENROUTER_API_KEY` to `~/.hermes/.env` (or `hermes config set OPENROUTER_API_KEY ...`).
3. Create the cron job: `hermes cron create '0 7 * * *' --name openrouter-fallback-rotator --script openrouter_fallback_check.py --no-agent --deliver telegram`.
4. Prime the fallback chain immediately with `python3 ~/.hermes/scripts/openrouter_fallback_check.py`.
5. Confirm `hermes config get fallback_providers` is non-empty.

## Verification

1. Run once with a valid OpenRouter key.
2. Run once with an invalid key and confirm fail-closed behavior.
3. Run again with the valid key and confirm idempotency.
4. Confirm `model.provider` and `model.default` are unchanged.
5. Confirm `fallback_providers` contains OpenRouter free models.
