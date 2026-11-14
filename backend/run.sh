#!/usr/bin/env bash
# Start the Sola backend (API + both frontends). Usage: backend/run.sh [port]
set -euo pipefail
cd "$(dirname "$0")"
VENV="${VENV:-../.venv}"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q -r requirements.txt
fi
exec "$VENV/bin/python" -m uvicorn app.main:app --host "${HOST:-127.0.0.1}" --port "${1:-${PORT:-8000}}"
