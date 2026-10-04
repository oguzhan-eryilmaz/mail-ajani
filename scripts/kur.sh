#!/bin/bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY="$REPO/.venv/bin/python"
LA="$HOME/Library/LaunchAgents"
DOMAIN="gui/$(id -u)"
mkdir -p "$LA" "$HOME/Library/Logs/mail-ajani"
for name in tur dinleyici; do
  label="com.oguzhan.mail-ajani.$name"
  sed -e "s|__PY__|$PY|g" -e "s|__REPO__|$REPO|g" -e "s|__HOME__|$HOME|g" \
    "$REPO/launchd/$label.plist" > "$LA/$label.plist"
  plutil -lint "$LA/$label.plist"
  launchctl bootout "$DOMAIN/$label" 2>/dev/null || true
  launchctl bootstrap "$DOMAIN" "$LA/$label.plist"
done
launchctl list | grep mail-ajani
