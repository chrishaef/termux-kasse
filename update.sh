#!/usr/bin/env bash
# Nach Verbindung mit Hotspot/WLAN: Repo aktualisieren, Abhängigkeiten synchronisieren,
# laufenden Uvicorn beenden und neu starten (Hintergrund + Log).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

export PORT="${PORT:-8000}"
NO_RESTART=0
for arg in "$@"; do
  case "$arg" in
    --no-restart) NO_RESTART=1 ;;
  esac
done

if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
else
  PYTHON=python
fi

echo ">>> Repository: $ROOT"

if [[ ! -d .git ]]; then
  echo "Fehler: Kein Git-Repository (.git fehlt)."
  exit 1
fi

echo ">>> git pull"
git pull --ff-only

if [[ ! -d .venv ]]; then
  echo ">>> Lege .venv an"
  "$PYTHON" -m venv .venv
fi
# shellcheck source=/dev/null
source .venv/bin/activate

echo ">>> pip install -r requirements.txt"
pip install -q -r requirements.txt

if [[ "$NO_RESTART" -eq 1 ]]; then
  echo "Fertig (--no-restart). Server manuell starten: bash start.sh"
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
  # Fallback, falls ohne PID-Datei gestartet wurde
  if command -v pkill >/dev/null 2>&1; then
    pkill -f "uvicorn app.main:app" 2>/dev/null || true
    sleep 1
  fi
}

stop_old

echo ">>> Starte Server (Hintergrund), Port ${PORT}"
nohup uvicorn app.main:app --host 127.0.0.1 --port "${PORT}" >>"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"

echo "Log: $LOG_FILE"
echo "URL:  http://127.0.0.1:${PORT}"
echo "PID: $(cat "$PID_FILE")"
echo "Stoppen (Beispiel): kill \$(cat .server.pid)   # im Projektroot ausführen"
