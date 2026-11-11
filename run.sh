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
  if [[ -n "$target_commit" && -n "$current_commit" ]] && git merge-base --is-ancestor "$target_commit" "$current_commit" 2>/dev/null; then
    echo ">>> Aktueller Stand enthält bereits den neuesten Release ($latest_tag). Kein Downgrade auf Tag-Stand."
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

release_run_lock() {
  rm -rf "$ROOT/.run.lock.dir" 2>/dev/null || true
}

acquire_run_lock() {
  # PID-based mkdir lock (not flock): older flock locks were inherited by
  # uvicorn via fd 9 and blocked every later admin update / run.sh forever.
  local LOCK_DIR="$ROOT/.run.lock.dir"
  local LOCK_PID_FILE="$LOCK_DIR/pid"
  local old_pid=""
  local i=0

  # Drop leftover flock file from older run.sh versions; it is unused now.
  rm -f "$ROOT/.run.lock" 2>/dev/null || true

  while [[ "$i" -lt 2 ]]; do
    if mkdir "$LOCK_DIR" 2>/dev/null; then
      echo $$ >"$LOCK_PID_FILE"
      trap 'release_run_lock' EXIT
      return 0
    fi
    old_pid="$(cat "$LOCK_PID_FILE" 2>/dev/null || true)"
    if [[ -n "${old_pid:-}" ]] && kill -0 "$old_pid" 2>/dev/null; then
      echo ">>> Start/Update läuft bereits in einer anderen Session (PID $old_pid) — Abbruch."
      exit 0
    fi
    echo ">>> Entferne verwaisten Start-Lock..."
    release_run_lock
    i=$((i + 1))
  done

  echo ">>> Start/Update läuft bereits in einer anderen Session — Abbruch."
  exit 0
}

server_pid_alive() {
  local PID_FILE="$ROOT/.server.pid"
  local PID=""
  if [[ ! -f "$PID_FILE" ]]; then
    return 1
  fi
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  [[ -n "${PID:-}" ]] && kill -0 "$PID" 2>/dev/null
}

server_port_open() {
  local py
  py="$ROOT/.venv/bin/python"
  if [[ ! -x "$py" ]]; then
    if command -v python3 >/dev/null 2>&1; then
      py=python3
    elif command -v python >/dev/null 2>&1; then
      py=python
    else
      return 1
    fi
  fi
  "$py" - "$PORT" <<'PY' >/dev/null 2>&1
import socket
import sys

port = int(sys.argv[1])
sock = socket.socket()
sock.settimeout(2)
try:
    sock.connect(("127.0.0.1", port))
except OSError:
    raise SystemExit(1)
finally:
    sock.close()
PY
}

server_already_running() {
  server_pid_alive && server_port_open
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

rotate_log_file() {
  local file="$1"
  local max_bytes="${2:-2000000}"
  local keep="${3:-5}"
  if [[ ! -f "$file" ]]; then
    return 0
  fi
  local size
  size="$(wc -c <"$file" 2>/dev/null || echo 0)"
  if [[ "$size" -lt "$max_bytes" ]]; then
    return 0
  fi
  local i
  for ((i=keep-1; i>=1; i--)); do
    if [[ -f "$file.$i" ]]; then
      mv -f "$file.$i" "$file.$((i+1))"
    fi
  done
  mv -f "$file" "$file.1"
}

start_server() {
  PID_FILE="$ROOT/.server.pid"
  LOG_FILE="$ROOT/server.log"
  rotate_log_file "$LOG_FILE" 2000000 5
  echo ">>> Starte Server (Hintergrund), Host ${HOST}, Port ${PORT}"
  # Close inherited fds 9/10 so a future lock never sticks on the daemon.
  nohup "$ROOT/.venv/bin/uvicorn" app.main:app --host "${HOST}" --port "${PORT}" --no-access-log 9>&- 10>&- >>"$LOG_FILE" 2>&1 &
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
acquire_run_lock
ensure_system_packages
pick_python
ensure_venv
ensure_master_password_files
echo ">>> Verwende Python: $(${PYTHON} --version 2>&1)"

DID_UPDATE=0
if [[ -d .git ]] && is_origin_reachable; then
  echo ">>> Verbindung zu GitHub erkannt: Update wird durchgeführt (Modus: $UPDATE_MODE)"
  echo ">>> Hole Remote-Referenzen"
  git fetch --tags --prune origin "+refs/heads/*:refs/remotes/origin/*"
  BEFORE_HEAD="$(git rev-parse HEAD 2>/dev/null || true)"
  if [[ "$UPDATE_MODE" == "commit" ]]; then
    sync_to_latest_commit
  else
    sync_to_latest_release
  fi
  AFTER_HEAD="$(git rev-parse HEAD 2>/dev/null || true)"
  echo ">>> pip install -r requirements.txt"
  pip install -q -r requirements.txt
  date +"%Y-%m-%d %H:%M:%S" > "$ROOT/.last_sync"
  if [[ -n "$BEFORE_HEAD" && -n "$AFTER_HEAD" && "$BEFORE_HEAD" != "$AFTER_HEAD" ]]; then
    DID_UPDATE=1
  fi
else
  echo ">>> Keine Verbindung zu GitHub: Starte ohne Update."
fi

if [[ "$DID_UPDATE" -eq 0 ]] && server_already_running; then
  echo ">>> Server läuft bereits (PID $(cat "$ROOT/.server.pid")) — kein erneuter Start."
  echo "lokal:  http://127.0.0.1:${PORT}"
  exit 0
fi

stop_old
start_server
