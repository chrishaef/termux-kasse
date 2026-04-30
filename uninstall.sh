#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOOT_SCRIPT="$HOME/.termux/boot/start-shopkasse.sh"
START_WIDGET="$HOME/.shortcuts/shopkasse-start.sh"
STOP_WIDGET="$HOME/.shortcuts/shopkasse-stop.sh"
STATUS_WIDGET="$HOME/.shortcuts/shopkasse-status.sh"

is_termux() {
  [[ -n "${TERMUX_VERSION:-}" ]]
}

if ! is_termux; then
  echo "Fehler: uninstall.sh ist nur für Termux gedacht."
  exit 1
fi

echo ">>> Shopkasse Deinstallation (Autostart/Widget-Einträge)"
echo ">>> Projekt: $ROOT"

bash "$ROOT/stop.sh" || true

rm -f "$BOOT_SCRIPT"
rm -f "$START_WIDGET" "$STOP_WIDGET" "$STATUS_WIDGET"

echo
echo "Entfernt:"
echo "- $BOOT_SCRIPT"
echo "- $START_WIDGET"
echo "- $STOP_WIDGET"
echo "- $STATUS_WIDGET"
echo
echo "Hinweis: Termux, Termux:Boot und Termux:Widget Apps selbst bleiben installiert."
