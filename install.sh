#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOOT_DIR="$HOME/.termux/boot"
BOOT_SCRIPT="$BOOT_DIR/start-shopkasse.sh"
SHORTCUTS_DIR="$HOME/.shortcuts"
START_WIDGET="$SHORTCUTS_DIR/shopkasse-start.sh"
STOP_WIDGET="$SHORTCUTS_DIR/shopkasse-stop.sh"
STATUS_WIDGET="$SHORTCUTS_DIR/shopkasse-status.sh"

is_termux() {
  [[ -n "${TERMUX_VERSION:-}" ]]
}

if ! is_termux; then
  echo "Fehler: install.sh ist nur für Termux gedacht."
  exit 1
fi

echo ">>> Shopkasse Erstinstallation (Termux)"
echo ">>> Projekt: $ROOT"

chmod +x "$ROOT/run.sh" "$ROOT/stop.sh" "$ROOT/setup_boot.sh" "$ROOT/install.sh" "$ROOT/uninstall.sh" 2>/dev/null || true

mkdir -p "$BOOT_DIR"
cat >"$BOOT_SCRIPT" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
cd "$ROOT"
bash "$ROOT/run.sh"
EOF
chmod 700 "$BOOT_SCRIPT"

mkdir -p "$SHORTCUTS_DIR"

cat >"$START_WIDGET" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
cd "$ROOT"
bash "$ROOT/run.sh"
EOF
chmod 700 "$START_WIDGET"

cat >"$STOP_WIDGET" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
cd "$ROOT"
bash "$ROOT/stop.sh"
EOF
chmod 700 "$STOP_WIDGET"

cat >"$STATUS_WIDGET" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
ROOT="$ROOT"
PID_FILE="\$ROOT/.server.pid"
PORT="\${PORT:-8000}"
HOST="\${HOST:-0.0.0.0}"

echo "Shopkasse Status"
echo "Projekt: \$ROOT"
echo
if [[ -f "\$PID_FILE" ]]; then
  PID="\$(cat "\$PID_FILE" || true)"
  if [[ -n "\${PID:-}" ]] && kill -0 "\$PID" 2>/dev/null; then
    echo "Server: läuft (PID \$PID)"
  else
    echo "Server: nicht aktiv (stale PID-Datei)"
  fi
else
  echo "Server: nicht aktiv (keine PID-Datei)"
fi
echo "URL lokal: http://127.0.0.1:\$PORT"
if [[ "\$HOST" == "0.0.0.0" ]]; then
  echo "LAN: http://<IP-des-Geräts>:\$PORT"
fi
EOF
chmod 700 "$STATUS_WIDGET"

echo
echo "Fertig:"
echo "- Termux:Boot Script: $BOOT_SCRIPT"
echo "- Termux:Widget Scripts:"
echo "  $START_WIDGET"
echo "  $STOP_WIDGET"
echo "  $STATUS_WIDGET"
echo
echo "Wichtig:"
echo "1) Termux, Termux:Boot und Termux:Widget installieren und jeweils einmal öffnen."
echo "2) Akku-Optimierung für Termux + Termux:Boot deaktivieren."
echo "3) Widget ggf. neu hinzufügen, damit neue Einträge sichtbar sind."
echo "4) Danach normal starten mit: bash \"$ROOT/run.sh\""
