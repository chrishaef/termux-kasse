#!/usr/bin/env bash
# Install + Update: Systemvoraussetzungen prüfen/ggf. installieren, Repo pullen,
# Python-Deps, Server neu starten (Hintergrund) — gedacht für Hotspot/WLAN.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

export PORT="${PORT:-8000}"
# Standard: LAN (0.0.0.0). Nur localhost: HOST=127.0.0.1
export HOST="${HOST:-0.0.0.0}"
NO_RESTART=0
NO_SYSTEM_INSTALL=0
for arg in "$@"; do
  case "$arg" in
    --no-restart) NO_RESTART=1 ;;
    --no-system-install) NO_SYSTEM_INSTALL=1 ;;
  esac
done

is_termux() {
  [[ -n "${TERMUX_VERSION:-}" ]]
}

is_apt() {
  command -v apt-get >/dev/null 2>&1
}

pick_python() {
  if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
  elif command -v python >/dev/null 2>&1; then
    PYTHON=python
  else
    echo "Fehler: Kein python3/python nach der Installation gefunden."
    exit 1
  fi
}

ensure_system_packages() {
  local need_git=0 need_py=0
  command -v git >/dev/null 2>&1 || need_git=1
  if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
    need_py=1
  fi

  if [[ "$need_git" -eq 0 && "$need_py" -eq 0 ]]; then
    echo ">>> System: git und Python sind vorhanden."
    return 0
  fi

  if [[ "$NO_SYSTEM_INSTALL" -eq 1 ]]; then
    echo "Fehler: git und/oder Python fehlt. Ohne --no-system-install erneut ausführen oder manuell installieren."
    exit 1
  fi

  if is_termux; then
    echo ">>> Termux: Paketlisten + Installation (git, python) — braucht Internet…"
    pkg update -y
    pkg install -y git python
  elif is_apt; then
    echo ">>> Debian/Ubuntu (apt): Installation (git, python3, venv, pip) — braucht Internet…"
    if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
      apt-get update -y
      apt-get install -y git python3 python3-venv python3-pip ca-certificates
    elif command -v sudo >/dev/null 2>&1; then
      sudo apt-get update -y
      sudo apt-get install -y git python3 python3-venv python3-pip ca-certificates
    else
      echo "Fehler: apt gefunden, aber weder root noch sudo. Bitte als root ausführen oder Pakete manuell installieren."
      exit 1
    fi
  else
    echo "Fehler: Weder Termux noch apt-get erkannt. Bitte manuell installieren: git, Python 3 inkl. venv und pip."
    exit 1
  fi

  command -v git >/dev/null 2>&1 || {
    echo "Fehler: git ist nach der Installation nicht verfügbar."
    exit 1
  }
  pick_python
  command -v "$PYTHON" >/dev/null 2>&1 || {
    echo "Fehler: Python ist nach der Installation nicht verfügbar."
    exit 1
  }
}

echo ">>> Projekt: $ROOT"

ensure_system_packages
pick_python
echo ">>> Verwende Python: $(${PYTHON} --version 2>&1)"

if [[ ! -d .git ]]; then
  echo "Fehler: Kein Git-Repository (.git fehlt). Zuerst klonen, dann update.sh im Projektroot ausführen."
  exit 1
fi

echo ">>> git pull"
git pull --ff-only
date +"%Y-%m-%d %H:%M:%S" > "$ROOT/.last_sync"

VENV_DIR="$ROOT/.venv"
VENV_ACTIVATE="$VENV_DIR/bin/activate"
if [[ ! -f "$VENV_ACTIVATE" ]]; then
  if [[ -d "$VENV_DIR" ]]; then
    echo ">>> .venv unvollständig (kein bin/activate) — wird neu angelegt"
    rm -rf "$VENV_DIR"
  fi
  echo ">>> Lege virtuelle Umgebung (.venv) an"
  if ! "$PYTHON" -m venv "$VENV_DIR"; then
    echo "Fehler: python -m venv ist fehlgeschlagen."
    echo "Debian/Ubuntu: sudo apt-get install -y python3-venv python3-pip"
    echo "Termux: pkg install python"
    exit 1
  fi
fi
if [[ ! -f "$VENV_ACTIVATE" ]]; then
  echo "Fehler: Erwartet $VENV_ACTIVATE — bitte .venv löschen und erneut ausführen."
  exit 1
fi
# shellcheck source=/dev/null
source "$VENV_ACTIVATE"

echo ">>> pip install -r requirements.txt"
pip install -q -r requirements.txt

if [[ "$NO_RESTART" -eq 1 ]]; then
  echo "Fertig (--no-restart). Server starten: bash start.sh  oder erneut: bash update.sh"
  exit 0
fi

PID_FILE="$ROOT/.server.pid"
LOG_FILE="$ROOT/server.log"

stop_old() {
  if [[ -f "$PID_FILE" ]]; then
    OLD_PID="$(cat "$PID_FILE" || true)"
    if [[ -n "${OLD_PID:-}" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
      echo ">>> Beende bisherigen Server (PID $OLD_PID)"
      kill "$OLD_PID" 2>/dev/null || true
      sleep 1
    fi
    rm -f "$PID_FILE"
  fi
  if command -v pkill >/dev/null 2>&1; then
    pkill -f "uvicorn app.main:app" 2>/dev/null || true
    sleep 1
  fi
}

stop_old

echo ">>> Starte Server (Hintergrund), Host ${HOST}, Port ${PORT}"
nohup "$ROOT/.venv/bin/uvicorn" app.main:app --host "${HOST}" --port "${PORT}" >>"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"

echo "Log: $LOG_FILE"
echo "lokal:  http://127.0.0.1:${PORT}"
if [[ "$HOST" == "0.0.0.0" ]]; then
  echo "LAN:    http://<IP-dieses-Rechners>:${PORT}"
else
  echo "Bind:   ${HOST}:${PORT}"
fi
echo "PID: $(cat "$PID_FILE")"
echo "Stoppen (Beispiel): kill \$(cat .server.pid)   # im Projektroot ausführen"
