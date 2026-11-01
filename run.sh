#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8788}"
VERSION="$(cat VERSION 2>/dev/null || echo '1.1.0')"
echo "🚀 Starting PulseMonitor v${VERSION} on http://${HOST}:${PORT}"
exec .venv/bin/uvicorn app:app --host "${HOST}" --port "${PORT}"
