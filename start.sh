#!/usr/bin/env bash
# Boots the local dev stack: MongoDB (only if nothing already answers on the
# port), the FastAPI backend on 8001 and the Next.js frontend on 3000.
# Ctrl+C stops both servers.
#
# Usage:  ./start.sh
# Ports can be overridden: BACKEND_PORT=8002 FRONTEND_PORT=3001 ./start.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8001}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
MONGO_PORT="${MONGO_PORT:-27017}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"

BACKEND_PID=""
FRONTEND_PID=""

step() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*" >&2; }
die() {
  printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2
  exit 1
}

# Returns 0 when something is listening on the given localhost TCP port.
port_open() {
  (exec 3<>"/dev/tcp/127.0.0.1/$1") >/dev/null 2>&1
}

# PIDs listening on the given TCP port, one per line.
listeners() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti "tcp:$1" -sTCP:LISTEN 2>/dev/null || true
  elif command -v fuser >/dev/null 2>&1; then
    fuser -n tcp "$1" 2>/dev/null | tr -s ' ' '\n' | grep -E '^[0-9]+$' || true
  fi
}

# Takes the port back: SIGTERM the current listener, escalate to SIGKILL if it
# refuses to let go. A stale server from a previous run must not block startup.
free_port() {
  local port="$1" label="$2" pids attempt
  pids="$(listeners "$port")"
  [ -z "$pids" ] && return 0

  warn "port $port ($label) is held by PID(s) $(echo "$pids" | tr '\n' ' ')— stopping them"
  # shellcheck disable=SC2086 # intentional word splitting: one PID per line
  kill $pids 2>/dev/null || true

  for attempt in 1 2 3 4 5; do
    port_open "$port" || return 0
    sleep 1
  done

  pids="$(listeners "$port")"
  if [ -n "$pids" ]; then
    warn "port $port did not free up — sending SIGKILL"
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null || true
    sleep 1
  fi
  port_open "$port" && die "could not free port $port"
  return 0
}

require() {
  command -v "$1" >/dev/null 2>&1 || die "$1 not found on PATH — $2"
}

# uv/npm spawn the real servers as children, so signal the whole subtree.
kill_tree() {
  local pid="$1" child
  for child in $(pgrep -P "$pid" 2>/dev/null || true); do
    kill_tree "$child"
  done
  kill "$pid" 2>/dev/null || true
}

cleanup() {
  trap - INT TERM EXIT
  # Nothing was started yet (e.g. a failed prerequisite check) — stay quiet.
  if [ -z "$BACKEND_PID" ] && [ -z "$FRONTEND_PID" ]; then
    return
  fi
  echo
  step 'shutting down'
  [ -n "$FRONTEND_PID" ] && kill_tree "$FRONTEND_PID"
  [ -n "$BACKEND_PID" ] && kill_tree "$BACKEND_PID"
  wait >/dev/null 2>&1 || true
}

# Ctrl+C is a normal way to end the session, not a failure.
on_signal() {
  cleanup
  exit 0
}
trap on_signal INT TERM
trap cleanup EXIT

# --- prerequisites -----------------------------------------------------------
require uv 'install it with: curl -LsSf https://astral.sh/uv/install.sh | sh'
require npm 'install Node.js 20+ from https://nodejs.org'

free_port "$BACKEND_PORT" backend
free_port "$FRONTEND_PORT" frontend

# --- dependencies ------------------------------------------------------------
step 'syncing backend dependencies (uv)'
uv sync --project "$ROOT_DIR/backend"

if [ ! -d "$ROOT_DIR/frontend/node_modules" ]; then
  step 'installing frontend dependencies (npm)'
  (cd "$ROOT_DIR/frontend" && npm install)
fi

# --- env files ---------------------------------------------------------------
step 'checking env files'
BACKEND_PORT="$BACKEND_PORT" uv run --project "$ROOT_DIR/backend" \
  python "$ROOT_DIR/tools/init_env.py"

# --- infrastructure ----------------------------------------------------------
MONGO_URL="$(sed -n 's/^MONGO_URL=//p' "$ROOT_DIR/.env" | head -1)"
case "${MONGO_URL:-mongodb://localhost}" in
*localhost* | *127.0.0.1*)
  if port_open "$MONGO_PORT"; then
    step "mongodb already listening on $MONGO_PORT — leaving it alone"
  elif command -v docker >/dev/null 2>&1; then
    step 'starting mongodb (docker compose)'
    (cd "$ROOT_DIR" && docker compose up -d mongo)
  else
    warn "nothing is listening on $MONGO_PORT and docker is unavailable — the backend will fail to connect"
  fi
  ;;
*)
  step 'MONGO_URL points at a remote host — skipping local mongodb'
  ;;
esac

port_open "$OLLAMA_PORT" ||
  warn "ollama is not answering on $OLLAMA_PORT — reviews will fail until 'ollama serve' is running"

# --- servers -----------------------------------------------------------------
step "backend  -> http://localhost:$BACKEND_PORT/docs"
cd "$ROOT_DIR/backend"
uv run uvicorn app.main:app --reload --port "$BACKEND_PORT" &
BACKEND_PID=$!

step "frontend -> http://localhost:$FRONTEND_PORT"
cd "$ROOT_DIR/frontend"
npm run dev -- --port "$FRONTEND_PORT" &
FRONTEND_PID=$!

echo
step 'both servers are up — press Ctrl+C to stop'

# Exit as soon as either server dies so the other one does not linger.
while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done

warn 'one of the servers exited'
