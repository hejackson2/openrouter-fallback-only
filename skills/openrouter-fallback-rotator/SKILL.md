---
name: openrouter-fallback-rotator
description: "Use when ranking OpenRouter free-model fallbacks."
version: 1.1.0
author: Ed Jackson (hejackson2), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [hermes, cron, openrouter, config, automation, fallback]
    related_skills: [hermes-agent]
---

# OpenRouter Fallback Rotator

Use this skill when you need to build, inspect, or rerun the deterministic Hermes cron that selects the best OpenRouter free models and writes them into Hermes fallback config. This version preserves the primary model, supports an optional capability tier list, and leaves cron-job repinning disabled unless you explicitly turn it on.

## When to Use

- You want Hermes fallback_providers refreshed from OpenRouter free models.
- You need to inspect why one free model ranked above another.
- You want to bias the rotator toward stronger free models with a local tier file.
- You want selected cron jobs pinned to the current top fallback, but only when you explicitly enable that behavior.
- Don't use for: changing the primary model or editing provider credentials.

## Prerequisites

- `OPENROUTER_API_KEY` must exist in `~/.hermes/.env` or the environment.
- Run the repo installer with `terminal(command="bash install.sh", workdir="<repo-root>")` before using the cron job from a fresh Hermes install.
- Optional: copy `openrouter_tiers.example.json` to `~/.hermes/openrouter_tiers.json` and edit scores.

## How to Run

- `terminal(command="python3 ~/.hermes/scripts/openrouter_fallback_check.py", timeout=120)`
- `terminal(command="hermes fallback list", timeout=120)`
- `terminal(command="python3 ~/.hermes/scripts/pin_cron_to_first_fallback.py", timeout=120)`
- `terminal(command="OPENROUTER_SYNC_CRON_PINS=1 python3 ~/.hermes/scripts/openrouter_fallback_check.py", timeout=120)`

## Quick Reference

- Refresh chain now: `terminal(command="python3 ~/.hermes/scripts/openrouter_fallback_check.py", timeout=120)`
- Show effective chain: `terminal(command="hermes fallback list", timeout=120)`
- Install the packaged files: `terminal(command="bash install.sh", workdir="<repo-root>", timeout=120)`
- Override chain length: `terminal(command="OPENROUTER_FALLBACK_CHAIN_LENGTH=5 python3 ~/.hermes/scripts/openrouter_fallback_check.py", timeout=120)`
- Use a custom tier file: `terminal(command="HERMES_TIER_CONFIG_PATH=~/.hermes/openrouter_tiers.json python3 ~/.hermes/scripts/openrouter_fallback_check.py", timeout=120)`
- Enable repinning for a run: `terminal(command="OPENROUTER_SYNC_CRON_PINS=1 python3 ~/.hermes/scripts/openrouter_fallback_check.py", timeout=120)`

## Procedure

1. Verify `OPENROUTER_API_KEY` is available and the script is installed. Completion criterion: `python3 ~/.hermes/scripts/openrouter_fallback_check.py` can start without a missing-key error.
2. Optionally create `~/.hermes/openrouter_tiers.json` from `openrouter_tiers.example.json` and adjust model scores. Completion criterion: the JSON parses and the desired models have the intended scores.
3. Run the rotator script. Completion criterion: it prints either `no change` or a refreshed fallback list with fetched and eligible counts.
4. Confirm `fallback_providers` changed as expected without rewriting `model.provider` or `model.default`. Completion criterion: `hermes fallback list` shows the intended order and the primary model is unchanged.
5. If cron pinning is desired, enable it explicitly for that run with `OPENROUTER_SYNC_CRON_PINS=1` and then review the helper output or run the pin helper directly. Completion criterion: each target cron job reports success or a clear failure reason.

## Pitfalls

- The tier file is optional, but malformed JSON is a hard failure by design.
- Models not present in the tier file receive the default score of 1 and are usually excluded by the default minimum tier score.
- The helper script pins specific cron job IDs; those IDs are local-environment details and may need editing for another user.
- Automatic cron repinning is off by default; set `OPENROUTER_SYNC_CRON_PINS=1` only if you explicitly want the rotator to rewrite job pins.
- If fewer than the requested number of eligible models survive filtering, the script fails closed and leaves config untouched.

## Verification

1. Run once with a valid OpenRouter key and confirm `fallback_providers` is populated.
2. Run again with the same inputs and confirm the script reports `no change`.
3. Verify the state file records the selected models and threshold settings.
4. Verify the primary model/provider block in Hermes config is unchanged.
