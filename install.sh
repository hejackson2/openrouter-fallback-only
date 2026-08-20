#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HERMES_HOME=${HERMES_HOME:-$HOME/.hermes}

mkdir -p "$HERMES_HOME/scripts" "$HERMES_HOME/skills/automation/openrouter-fallback-rotator"
cp "$ROOT_DIR/scripts/openrouter_fallback_check.py" "$HERMES_HOME/scripts/openrouter_fallback_check.py"
cp "$ROOT_DIR/skills/openrouter-fallback-rotator/SKILL.md" "$HERMES_HOME/skills/automation/openrouter-fallback-rotator/SKILL.md"
chmod +x "$HERMES_HOME/scripts/openrouter_fallback_check.py"

echo "Installed:"
echo "  $HERMES_HOME/scripts/openrouter_fallback_check.py"
echo "  $HERMES_HOME/skills/automation/openrouter-fallback-rotator/SKILL.md"
echo
echo "Optional env knob: OPENROUTER_FALLBACK_CHAIN_LENGTH=3"
echo
echo "Next step: register the cron job with:"
echo "  hermes cron create '0 7 * * *' --name openrouter-fallback-rotator --script openrouter_fallback_check.py --no-agent --deliver telegram"
