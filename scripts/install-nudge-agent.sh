#!/usr/bin/env bash
# Install the pre-kickoff nudge launchd agent.
#
# Usage:
#   FANTASY_GM_WEEK=7 FANTASY_GM_SEASON=2026 ./scripts/install-nudge-agent.sh
#
# To uninstall:
#   launchctl unload ~/Library/LaunchAgents/com.fantasygm.nudge.plist
#   rm ~/Library/LaunchAgents/com.fantasygm.nudge.plist
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_SRC="$REPO_ROOT/resources/com.fantasygm.nudge.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.fantasygm.nudge.plist"
PYTHON="$REPO_ROOT/.venv/bin/python"
WEEK="${FANTASY_GM_WEEK:?Set FANTASY_GM_WEEK before running this script}"
SEASON="${FANTASY_GM_SEASON:-2026}"
THRESHOLD="${FANTASY_GM_NUDGE_THRESHOLD_MINUTES:-120}"

if [[ ! -f "$PYTHON" ]]; then
  echo "ERROR: no venv python at $PYTHON — run 'uv sync' first" >&2
  exit 1
fi

# Write the resolved plist, substituting placeholders.
sed \
  -e "s|PYTHON_PLACEHOLDER|$PYTHON|g" \
  -e "s|REPO_ROOT_PLACEHOLDER|$REPO_ROOT|g" \
  "$PLIST_SRC" > "$PLIST_DEST"

# Inject env vars the CLI needs (week and season change each week).
/usr/libexec/PlistBuddy -c "Add :EnvironmentVariables dict" "$PLIST_DEST" 2>/dev/null || true
/usr/libexec/PlistBuddy \
  -c "Set :EnvironmentVariables:FANTASY_GM_REPO $REPO_ROOT" \
  -c "Set :EnvironmentVariables:FANTASY_GM_WEEK $WEEK" \
  -c "Set :EnvironmentVariables:FANTASY_GM_SEASON $SEASON" \
  -c "Set :EnvironmentVariables:FANTASY_GM_NUDGE_THRESHOLD_MINUTES $THRESHOLD" \
  "$PLIST_DEST"

# Reload (unload first to pick up any change).
launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load "$PLIST_DEST"

echo "Nudge agent installed. Fires every 15 min Sunday 9 AM–1 PM."
echo "  Week: $WEEK  Season: $SEASON  Threshold: ${THRESHOLD}m"
echo "  Log:  $REPO_ROOT/data/nudge.log"
echo ""
echo "To uninstall:"
echo "  launchctl unload $PLIST_DEST && rm $PLIST_DEST"
