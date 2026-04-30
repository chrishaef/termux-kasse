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

ensure_allow_external_apps_enabled() {
  local TERMUX_DIR="$HOME/.termux"
  local PROPS_FILE="$TERMUX_DIR/termux.properties"
  local TMP_FILE
  mkdir -p "$TERMUX_DIR"

  if [[ ! -f "$PROPS_FILE" ]]; then
    printf "allow-external-apps = true\n" >"$PROPS_FILE"
    echo ">>> Termux-Property gesetzt: allow-external-apps = true"
    return 0
  fi

  if grep -Eq '^[[:space:]]*allow-external-apps[[:space:]]*=' "$PROPS_FILE"; then
    TMP_FILE="$(mktemp)"
    awk '
      BEGIN { done=0 }
      /^[[:space:]]*allow-external-apps[[:space:]]*=/ {
        if (!done) {
          print "allow-external-apps = true"
          done=1
        }
        next
      }
      { print }
      END {
        if (!done) {
          print "allow-external-apps = true"
        }
      }
    ' "$PROPS_FILE" >"$TMP_FILE"
    mv "$TMP_FILE" "$PROPS_FILE"
    echo ">>> Termux-Property aktualisiert: allow-external-apps = true"
    return 0
  fi

  if grep -Eq '^[[:space:]]*#?[[:space:]]*allow-external-apps[[:space:]]*=' "$PROPS_FILE"; then
    TMP_FILE="$(mktemp)"
    awk '
      BEGIN { done=0 }
      /^[[:space:]]*#?[[:space:]]*allow-external-apps[[:space:]]*=/ {
        if (!done) {
          print "allow-external-apps = true"
          done=1
        }
        next
      }
      { print }
      END {
        if (!done) {
          print "allow-external-apps = true"
        }
      }
    ' "$PROPS_FILE" >"$TMP_FILE"
    mv "$TMP_FILE" "$PROPS_FILE"
    echo ">>> Termux-Property aktiviert: allow-external-apps = true"
    return 0
  fi

  printf "\nallow-external-apps = true\n" >>"$PROPS_FILE"
  echo ">>> Termux-Property ergänzt: allow-external-apps = true"
}

if ! is_termux; then
  echo "Fehler: install.sh ist nur für Termux gedacht."
  exit 1
fi

echo ">>> Shopkasse Erstinstallation (Termux)"
echo ">>> Projekt: $ROOT"

chmod +x "$ROOT/run.sh" "$ROOT/stop.sh" "$ROOT/install.sh" "$ROOT/uninstall.sh" 2>/dev/null || true
ensure_allow_external_apps_enabled

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
echo
if [[ -t 0 ]]; then
  read -r -p "Enter drücken zum Schließen..." _
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
echo "4) Termux einmal neu öffnen oder 'termux-reload-settings' ausführen."
echo "5) Danach normal starten mit: bash \"$ROOT/run.sh\""
