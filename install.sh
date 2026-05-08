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

is_origin_reachable() {
  if [[ ! -d "$ROOT/.git" ]]; then
    return 1
  fi
  git -C "$ROOT" ls-remote --exit-code --heads origin >/dev/null 2>&1
}

latest_release_tag() {
  git -C "$ROOT" tag --list "v[0-9]*.[0-9]*.[0-9]*" --sort=-version:refname | sed -n '1p'
}

sync_to_latest_release() {
  local latest_tag current_commit target_commit
  if [[ ! -d "$ROOT/.git" ]]; then
    return 0
  fi
  if ! is_origin_reachable; then
    echo ">>> Kein Zugriff auf GitHub/origin. Release-Update beim Install übersprungen."
    return 0
  fi
  echo ">>> Suche neuesten offiziellen Release..."
  git -C "$ROOT" fetch --tags --prune origin
  latest_tag="$(latest_release_tag)"
  if [[ -z "$latest_tag" ]]; then
    echo ">>> Kein offizieller Release-Tag gefunden. Aktueller Stand bleibt unverändert."
    return 0
  fi
  target_commit="$(git -C "$ROOT" rev-list -n 1 "$latest_tag" 2>/dev/null || true)"
  current_commit="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)"
  if [[ -n "$target_commit" && "$current_commit" == "$target_commit" ]]; then
    echo ">>> Bereits auf aktuellem Release: $latest_tag"
    return 0
  fi
  if [[ -n "$target_commit" && -n "$current_commit" ]] && git -C "$ROOT" merge-base --is-ancestor "$target_commit" "$current_commit" 2>/dev/null; then
    echo ">>> Aktueller Stand enthält bereits den neuesten Release ($latest_tag). Kein Downgrade auf Tag-Stand."
    return 0
  fi
  echo ">>> Wechsle auf neuesten offiziellen Release: $latest_tag"
  git -C "$ROOT" checkout -f "$latest_tag"
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
sync_to_latest_release
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
echo "=== Shopkasse: Start/Update ==="
echo "Projekt: $ROOT"
echo "Zeit: \$(date '+%Y-%m-%d %H:%M:%S')"
echo
if bash "$ROOT/run.sh"; then
  echo
  echo "Ergebnis: Start/Update erfolgreich."
else
  echo
  echo "Ergebnis: Start/Update fehlgeschlagen."
fi
echo
echo "Wechsle zur SBrowser-App in 3 Sekunden..."
sleep 3
if command -v am >/dev/null 2>&1; then
  am start -n com.example.s_browser/.MainActivity >/dev/null 2>&1 || \
    monkey -p com.example.s_browser -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true
fi
EOF
chmod 700 "$START_WIDGET"

cat >"$STOP_WIDGET" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
cd "$ROOT"
echo "=== Shopkasse: Stop ==="
echo "Projekt: $ROOT"
echo "Zeit: \$(date '+%Y-%m-%d %H:%M:%S')"
echo
if bash "$ROOT/stop.sh"; then
  echo
  echo "Ergebnis: System wurde gestoppt."
else
  echo
  echo "Ergebnis: Stop meldete einen Fehler."
fi
echo
echo "Termux wird in 3 Sekunden geschlossen..."
sleep 3
if command -v am >/dev/null 2>&1; then
  am force-stop com.termux >/dev/null 2>&1 || \
    am start -a android.intent.action.MAIN -c android.intent.category.HOME >/dev/null 2>&1 || true
fi
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
echo "Zeit: \$(date '+%Y-%m-%d %H:%M:%S')"
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
if [[ -d "\$ROOT/.git" ]] && command -v git >/dev/null 2>&1; then
  CURRENT_TAG="\$(git -C "\$ROOT" describe --tags --exact-match 2>/dev/null || true)"
  LATEST_TAG="\$(git -C "\$ROOT" tag --list "v[0-9]*.[0-9]*.[0-9]*" --sort=-version:refname | sed -n '1p')"
  if [[ -n "\$LATEST_TAG" ]]; then
    if [[ "\$CURRENT_TAG" == "\$LATEST_TAG" ]]; then
      echo "Update-Status: up to date (\$LATEST_TAG)"
    else
      echo "Update-Status: neuer offizieller Release verfügbar (\$LATEST_TAG)"
    fi
  else
    echo "Update-Status: kein offizieller Release-Tag gefunden."
  fi
else
  echo "Update-Status: nicht verfügbar (kein git repo)."
fi
echo
echo "Termux wird in 5 Sekunden minimiert..."
sleep 5
if command -v am >/dev/null 2>&1; then
  am start -a android.intent.action.MAIN -c android.intent.category.HOME >/dev/null 2>&1 || true
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
