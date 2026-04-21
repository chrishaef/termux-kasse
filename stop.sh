#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PID_FILE="$ROOT/.server.pid"
TARGET_PATTERN="uvicorn app.main:app"
stopped=0

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${PID:-}" ]] && kill -0 "$PID" 2>/dev/null; then
    echo ">>> Stoppe Server über PID-Datei ($PID)"
    kill "$PID" 2>/dev/null || true
    sleep 1
    if kill -0 "$PID" 2>/dev/null; then
      echo ">>> Prozess reagiert nicht, sende SIGKILL ($PID)"
      kill -9 "$PID" 2>/dev/null || true
    fi
    stopped=1
  fi
  rm -f "$PID_FILE"
fi

if command -v pkill >/dev/null 2>&1; then
  if pkill -f "$TARGET_PATTERN" 2>/dev/null; then
    echo ">>> Stoppe verbleibende Uvicorn-Prozesse per Pattern"
    stopped=1
  fi
fi

if [[ "$stopped" -eq 1 ]]; then
  echo ">>> Server gestoppt."
else
  echo ">>> Kein laufender Server gefunden."
fi
