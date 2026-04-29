#!/usr/bin/env bash
# Unified runner for Termux/Debian:
# - If GitHub/origin is reachable: pull + dependency update + restart server
# - If not reachable: start server without update
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

export PORT="${PORT:-8000}"
export HOST="${HOST:-0.0.0.0}"
NO_SYSTEM_INSTALL=0
for arg in "$@"; do
  case "$arg" in
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
    echo "Fehler: Kein python3/python gefunden."
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
    return 0
  fi

  if [[ "$NO_SYSTEM_INSTALL" -eq 1 ]]; then
    echo "Fehler: git und/oder Python fehlt. Ohne --no-system-install erneut ausführen oder manuell installieren."
    exit 1
  fi

  if is_termux; then
    echo ">>> Termux: installiere fehlende Pakete (git, python)"
    pkg update -y
    pkg install -y git python
  elif is_apt; then
    echo ">>> Debian/Ubuntu: installiere fehlende Pakete (git, python3, venv, pip)"
    if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
      apt-get update -y
      apt-get install -y git python3 python3-venv python3-pip ca-certificates
    elif command -v sudo >/dev/null 2>&1; then
      sudo apt-get update -y
      sudo apt-get install -y git python3 python3-venv python3-pip ca-certificates
    else
      echo "Fehler: apt gefunden, aber weder root noch sudo."
      exit 1
    fi
  else
    echo "Fehler: Weder Termux noch apt-get erkannt. Bitte manuell installieren: git, Python 3 inkl. venv/pip."
    exit 1
  fi
}

is_origin_reachable() {
  if [[ ! -d .git ]]; then
    return 1
  fi
  if ! command -v timeout >/dev/null 2>&1; then
    git ls-remote --exit-code --heads origin >/dev/null 2>&1
    return $?
  fi
  timeout 8 git ls-remote --exit-code --heads origin >/dev/null 2>&1
}

ensure_venv() {
  VENV_DIR="$ROOT/.venv"
  VENV_ACTIVATE="$VENV_DIR/bin/activate"
  if [[ ! -f "$VENV_ACTIVATE" ]]; then
    if [[ -d "$VENV_DIR" ]]; then
      rm -rf "$VENV_DIR"
    fi
    echo ">>> Lege virtuelle Umgebung (.venv) an"
    "$PYTHON" -m venv "$VENV_DIR"
  fi
  # shellcheck source=/dev/null
  source "$VENV_ACTIVATE"
}

ensure_master_password_files() {
  local MASTER_FILE="$ROOT/.master_pwd"
  local EXAMPLE_FILE="$ROOT/.master_pwd.example"
  if [[ ! -f "$EXAMPLE_FILE" ]]; then
    printf "master\n" >"$EXAMPLE_FILE"
  fi
  if [[ ! -f "$MASTER_FILE" ]]; then
    cp "$EXAMPLE_FILE" "$MASTER_FILE"
    echo ">>> .master_pwd wurde mit Standardwert erstellt (bitte im Live-Betrieb ändern)"
  fi
}

stop_old() {
  PID_FILE="$ROOT/.server.pid"
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

start_server() {
  PID_FILE="$ROOT/.server.pid"
  LOG_FILE="$ROOT/server.log"
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
}

echo ">>> Projekt: $ROOT"
ensure_system_packages
pick_python
ensure_venv
ensure_master_password_files
echo ">>> Verwende Python: $(${PYTHON} --version 2>&1)"

if [[ -d .git ]] && is_origin_reachable; then
  CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
  echo ">>> Verbindung zu GitHub erkannt: Update wird durchgeführt"
  echo ">>> Hole Remote-Tags für Versionsanzeige"
  git fetch --tags --prune origin || true
  git pull --ff-only origin "${CURRENT_BRANCH}"
  echo ">>> pip install -r requirements.txt"
  pip install -q -r requirements.txt
  date +"%Y-%m-%d %H:%M:%S" > "$ROOT/.last_sync"
else
  echo ">>> Keine Verbindung zu GitHub: Starte ohne Update."
fi

stop_old
start_server
