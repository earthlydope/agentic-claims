#!/usr/bin/env bash
# Start both halves of the platform and wait for them to come up.
set -euo pipefail
cd "$(dirname "$0")"

API_PORT="${API_PORT:-8099}"
WEB_PORT="${WEB_PORT:-5173}"

if [[ ! -x backend/.venv/bin/python ]]; then
  echo "No virtualenv found. Run: make install" >&2
  exit 1
fi

echo "→ API on :${API_PORT}"
(cd backend && .venv/bin/python -m uvicorn app.main:app --port "${API_PORT}" --log-level warning) &
API_PID=$!
trap 'kill ${API_PID} 2>/dev/null || true' EXIT

for _ in $(seq 1 40); do
  if curl -fsS -m 1 "http://127.0.0.1:${API_PORT}/api/health" >/dev/null 2>&1; then break; fi
  sleep 0.5
done

curl -fsS "http://127.0.0.1:${API_PORT}/api/health" || { echo "API failed to start" >&2; exit 1; }
echo
echo "→ Console on :${WEB_PORT}"
cd frontend && npm run dev -- --port "${WEB_PORT}"
