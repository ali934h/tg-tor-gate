#!/usr/bin/env bash
# Removes tg-tor-gate: the bot service, its files, and the torrc block it added.
# Tor itself and any config.py values you entered manually elsewhere are left alone.
set -euo pipefail

INSTALL_DIR="/root/tg-tor-gate"
SERVICE_FILE="/etc/systemd/system/tg-tor-gate.service"
TORRC="/etc/tor/torrc"

if [[ $EUID -ne 0 ]]; then
  echo "Run this as root." >&2
  exit 1
fi

echo "==> Stopping tg-tor-gate service…"
systemctl stop tg-tor-gate 2>/dev/null || true
systemctl disable tg-tor-gate 2>/dev/null || true
rm -f "$SERVICE_FILE"
systemctl daemon-reload

echo "==> Removing tg-tor-gate torrc block…"
if [[ -f "$TORRC" ]]; then
  sed -i '/# --- tg-tor-gate begin ---/,/# --- tg-tor-gate end ---/d' "$TORRC"
  systemctl restart tor 2>/dev/null || true
fi

echo "==> Removing files…"
rm -rf "$INSTALL_DIR"

echo "✓ tg-tor-gate removed. Tor itself was left installed and running."
