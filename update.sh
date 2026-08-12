#!/usr/bin/env bash
# Pulls the latest code, updates dependencies, and restarts the bot.
set -euo pipefail

INSTALL_DIR="/root/tg-tor-gate"

if [[ $EUID -ne 0 ]]; then
  echo "Run this as root." >&2
  exit 1
fi

cd "$INSTALL_DIR"
echo "==> Pulling latest code…"
git pull --quiet

echo "==> Updating dependencies…"
"$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade -r requirements.txt

echo "==> Restarting service…"
systemctl restart tg-tor-gate
sleep 2

if systemctl is-active --quiet tg-tor-gate; then
  echo "✓ Updated and running."
else
  echo "✗ Service failed to start — check: journalctl -u tg-tor-gate -e" >&2
  exit 1
fi
