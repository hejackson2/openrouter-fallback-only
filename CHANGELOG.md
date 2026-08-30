# Changelog

All notable changes to this project will be documented in this file.

The format is loosely based on Keep a Changelog and uses reverse chronological order.

## [Unreleased]

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
