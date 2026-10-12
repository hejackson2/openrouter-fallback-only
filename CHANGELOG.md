# Changelog

All notable changes to this project will be documented in this file.

The format is loosely based on Keep a Changelog and uses reverse chronological order.

## [Unreleased]

### Added
- Added `skills/openrouter-fallback-rotator/references/session-2026-08-29.md` reference notes capturing session background, trade-offs, and capability-based scoring design.

### Changed
- Added resilient YAML loader fallback chain to `scripts/openrouter_fallback_check.py` and `scripts/pin_cron_to_first_fallback.py`: attempts `yaml` (PyYAML), then `hermes_yaml`, then `ruamel.yaml`, preventing runtime failures on Hermes package updates or environments without PyYAML.
- Updated `scripts/openrouter_fallback_check.py` to resolve tier configuration path relative to `HERMES_HOME` when `HERMES_TIER_CONFIG_PATH` is not explicitly set.
- Updated `install.sh` to install references into the skill directory and seed `$HERMES_HOME/openrouter_tiers.json` if not already present.
- Updated `scripts/openrouter_fallback_check.py` to make cron-job repinning opt-in via `OPENROUTER_SYNC_CRON_PINS=1` instead of automatic.
- Updated `README.md` and `skills/openrouter-fallback-rotator/SKILL.md` to document that cron jobs follow the primary model by default unless repinning is explicitly enabled.

## [2026-08-30]

### Added
- Added `openrouter_tiers.example.json` to define example capability tiers for OpenRouter free models.
- Added `scripts/pin_cron_to_first_fallback.py` to repin selected cron jobs to the top fallback model.
- Added test coverage for tier-based ranking behavior and recorded thresholds in rotator state output.
- Added this `CHANGELOG.md` file for ongoing release notes.

### Changed
- Updated `scripts/openrouter_fallback_check.py` to support tier-based model scoring and eligibility filtering.
- Updated the rotator ranking logic to consider throttling status, tier score, context length, creation time, and stable model-id tie-breaking.
- Updated `install.sh` to install the pinning helper and example tier file.
- Updated `README.md` and `skills/openrouter-fallback-rotator/SKILL.md` to document the current tier-list workflow.

## [2026-08-20]

### Added
- Initial fallback-only OpenRouter rotator project.

### Changed
- Added install and fallback setup documentation.
