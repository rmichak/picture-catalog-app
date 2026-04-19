#!/usr/bin/env bash
# Dev launcher for macOS / Linux.
# Starts the backend (uvicorn) and the frontend (vite) in parallel and opens the browser.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -d backend/.venv ]; then
  echo "==> Creating Python venv (uv venv --python 3.12)"
  (cd backend && uv venv --python 3.12)
fi

echo "==> Installing backend deps"
(cd backend && uv pip install -e ".[dev]")

if [ ! -d frontend/node_modules ]; then
  echo "==> Installing frontend deps"
  (cd frontend && npm install)
fi

cleanup() {
  echo "==> Stopping..."
  kill $(jobs -p) 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "==> Starting backend on http://localhost:8000"
(cd backend && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload) &

echo "==> Starting frontend on http://localhost:5173"
(cd frontend && npm run dev) &

# macOS: open the browser to the Vite dev server
if command -v open >/dev/null 2>&1; then
  sleep 2
  open http://localhost:5173 || true
fi

wait
