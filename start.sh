#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

export PORT="${PORT:-8000}"

if [[ ! -d .venv ]]; then
  python -m venv .venv
fi
# shellcheck source=/dev/null
source .venv/bin/activate

if [[ "${1:-}" == "--sync" ]]; then
  pip install -r requirements.txt
fi

if ! python -c "import fastapi" 2>/dev/null; then
  echo "Dependencies missing. Run: bash start.sh --sync"
  exit 1
fi

echo "Vertrauenskasse: http://127.0.0.1:${PORT}"
exec uvicorn app.main:app --host 127.0.0.1 --port "${PORT}"
