#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HERMES_HOME=${HERMES_HOME:-$HOME/.hermes}
SCRIPT_PATH="$HERMES_HOME/scripts/openrouter_fallback_check.py"
SKILL_PATH="$HERMES_HOME/skills/automation/openrouter-fallback-rotator/SKILL.md"
CRON_CMD="hermes cron create '0 7 * * *' --name openrouter-fallback-rotator --script openrouter_fallback_check.py --no-agent --deliver telegram"
FIRST_RUN_CMD="python3 $SCRIPT_PATH"

mkdir -p "$HERMES_HOME/scripts" "$HERMES_HOME/skills/automation/openrouter-fallback-rotator"
cp "$ROOT_DIR/scripts/openrouter_fallback_check.py" "$SCRIPT_PATH"
cp "$ROOT_DIR/skills/openrouter-fallback-rotator/SKILL.md" "$SKILL_PATH"
chmod +x "$SCRIPT_PATH"

echo "Installed:"
echo "  $SCRIPT_PATH"
echo "  $SKILL_PATH"
echo
if [ -f "$HERMES_HOME/.env" ] && grep -q '^OPENROUTER_API_KEY=' "$HERMES_HOME/.env"; then
  echo "Detected OPENROUTER_API_KEY in $HERMES_HOME/.env"
else
  echo "OPENROUTER_API_KEY not found in $HERMES_HOME/.env"
  echo "Add it before the first run, for example:"
  echo "  hermes config set OPENROUTER_API_KEY sk-or-..."
  echo
fi

echo "Optional env knob: OPENROUTER_FALLBACK_CHAIN_LENGTH=3"
echo
echo "To enable automatic fallback when your primary model quota runs out:"
echo "  1) Keep your main model as-is (this script does not change model.provider/default)"
echo "  2) Register the cron job:"
echo "     $CRON_CMD"
echo "  3) Prime fallback_providers now by running:"
echo "     $FIRST_RUN_CMD"
echo "  4) Verify: hermes config get fallback_providers"
