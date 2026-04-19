#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

export PORT="${PORT:-8000}"
# Standard: alle LAN-Schnittstellen (Tablet/Container von anderen Geräten erreichbar).
# Nur dieses Gerät: HOST=127.0.0.1
export HOST="${HOST:-0.0.0.0}"

VENV_DIR="$ROOT/.venv"
VENV_ACTIVATE="$VENV_DIR/bin/activate"
if command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  PY=python
fi
if [[ ! -f "$VENV_ACTIVATE" ]]; then
  if [[ -d "$VENV_DIR" ]]; then
    echo ">>> .venv unvollständig — wird neu angelegt" >&2
    rm -rf "$VENV_DIR"
  fi
  "$PY" -m venv "$VENV_DIR" || {
    echo "venv fehlgeschlagen. Debian: apt install python3-venv" >&2
    exit 1
  }
fi
# shellcheck source=/dev/null
source "$VENV_ACTIVATE"

if [[ "${1:-}" == "--sync" ]]; then
  pip install -r requirements.txt
fi

if ! python -c "import fastapi" 2>/dev/null; then
  echo "Dependencies missing. Run: bash start.sh --sync"
  exit 1
fi

echo "Shopkasse (Port ${PORT}):"
echo "  lokal:    http://127.0.0.1:${PORT}"
if [[ "$HOST" == "0.0.0.0" ]]; then
  echo "  im LAN:   http://<IP-dieses-Rechners>:${PORT}"
else
  echo "  Bind:     ${HOST} (nur lokaler Zugriff)"
fi
exec uvicorn app.main:app --host "${HOST}" --port "${PORT}"
