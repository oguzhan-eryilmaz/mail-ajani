#!/bin/bash
set -uo pipefail
DOMAIN="gui/$(id -u)"
for name in tur dinleyici; do
  label="com.oguzhan.mail-ajani.$name"
  launchctl bootout "$DOMAIN/$label" 2>/dev/null
  rm -f "$HOME/Library/LaunchAgents/$label.plist"
done
echo "Kaldırıldı. Veriler duruyor: ~/Library/Application Support/mail-ajani"
