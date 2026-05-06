#!/usr/bin/env bash
# Unified runner for Termux/Debian:
# - If GitHub/origin is reachable: update to newest official release tag + dependency update + restart server
# - If not reachable: start server without update
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

export PORT="${PORT:-8000}"
export HOST="${HOST:-0.0.0.0}"
# Avoid noisy pip update notices during unattended startup.
export PIP_DISABLE_PIP_VERSION_CHECK="${PIP_DISABLE_PIP_VERSION_CHECK:-1}"
NO_SYSTEM_INSTALL=0
UPDATE_MODE="${UPDATE_MODE:-release}"
for arg in "$@"; do
  case "$arg" in
    --no-system-install) NO_SYSTEM_INSTALL=1 ;;
    --commit-update) UPDATE_MODE="commit" ;;
    --update-mode=release) UPDATE_MODE="release" ;;
    --update-mode=commit) UPDATE_MODE="commit" ;;
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

latest_release_tag() {
  git tag --list "v[0-9]*.[0-9]*.[0-9]*" --sort=-version:refname | sed -n '1p'
}

sync_to_latest_release() {
  local latest_tag current_commit target_commit
  latest_tag="$(latest_release_tag)"
  if [[ -z "$latest_tag" ]]; then
    echo ">>> Kein offizieller Release-Tag gefunden. Aktueller Stand bleibt unverändert."
    return 0
  fi
  target_commit="$(git rev-list -n 1 "$latest_tag" 2>/dev/null || true)"
  current_commit="$(git rev-parse HEAD 2>/dev/null || true)"
  if [[ -n "$target_commit" && "$current_commit" == "$target_commit" ]]; then
    echo ">>> Bereits auf aktuellem Release: $latest_tag"
    return 0
  fi
  echo ">>> Wechsle auf neuesten offiziellen Release: $latest_tag"
  git checkout -f "$latest_tag"
}

default_remote_branch() {
  local head_ref
  head_ref="$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null || true)"
  if [[ -n "$head_ref" ]]; then
    echo "${head_ref#origin/}"
    return 0
  fi
  echo "main"
}

sync_to_latest_commit() {
  local branch target_commit current_commit
  branch="$(default_remote_branch)"
  target_commit="$(git rev-parse "origin/$branch" 2>/dev/null || true)"
  if [[ -z "$target_commit" ]]; then
    echo ">>> Konnte origin/$branch nicht auflösen. Commit-Update übersprungen."
    return 0
  fi
  current_commit="$(git rev-parse HEAD 2>/dev/null || true)"
  if [[ "$current_commit" == "$target_commit" ]]; then
    echo ">>> Bereits auf aktuellem Commit von origin/$branch (${target_commit:0:7})"
    return 0
  fi
  echo ">>> Wechsle auf neuesten Commit von origin/$branch (${target_commit:0:7})"
  git checkout -B "$branch" "origin/$branch"
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
  echo ">>> Verbindung zu GitHub erkannt: Update wird durchgeführt (Modus: $UPDATE_MODE)"
  echo ">>> Hole Remote-Referenzen"
  git fetch --tags --prune origin "+refs/heads/*:refs/remotes/origin/*"
  if [[ "$UPDATE_MODE" == "commit" ]]; then
    sync_to_latest_commit
  else
    sync_to_latest_release
  fi
  echo ">>> pip install -r requirements.txt"
  pip install -q -r requirements.txt
  date +"%Y-%m-%d %H:%M:%S" > "$ROOT/.last_sync"
else
  echo ">>> Keine Verbindung zu GitHub: Starte ohne Update."
fi

stop_old
start_server
