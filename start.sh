#!/bin/bash
# GODFIN — Start/restart backend + frontend, then open in Chrome
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOGFILE="$SCRIPT_DIR/godfin_startup.log"

exec 2>> "$LOGFILE"

echo "=== GODFIN STARTUP $(date) ===" >> "$LOGFILE"

# Load user's PATH so uvicorn/npx/node/python3 are found when double-clicked
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/Library/Python/3.9/bin:$PATH"

# Get local IP for the optional network-access mode
LOCAL_IP=$(ifconfig | grep "inet " | grep -v 127.0.0.1 | head -1 | awk '{print $2}')
if [ -z "$LOCAL_IP" ]; then
    LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
fi

echo "========================================="
echo "  GODFIN — Starting up..."
echo "========================================="

# Kill any existing GODFIN processes
echo "  Stopping previous instances..."
lsof -ti:5100 2>/dev/null | xargs kill -9 2>/dev/null || true
lsof -ti:5200 2>/dev/null | xargs kill -9 2>/dev/null || true
sleep 1

# Resolve the explicit setting before starting either listener. The safe
# default is localhost; Settings can opt in to LAN access and request restart.
BIND_HOST=$(PYTHONPATH="$SCRIPT_DIR/backend" "$SCRIPT_DIR/backend/venv/bin/python" -m app.core.network_access)

# Backend — use venv's uvicorn directly
echo "  → Starting backend on port 5100"
cd "$SCRIPT_DIR/backend"
# Use full path to venv's uvicorn to avoid activation issues when double-clicked
"$SCRIPT_DIR/backend/venv/bin/uvicorn" app.main:app --host "$BIND_HOST" --port 5100 &
BACKEND_PID=$!

# Wait for backend to be ready before starting frontend
echo "  → Waiting for backend to be ready..."
for i in {1..30}; do
  if curl -s http://localhost:5100/api/v1/auth/status > /dev/null 2>&1 || curl -s -o /dev/null -w "%{http_code}" http://localhost:5100/ 2>&1 | grep -qE "^[2-4]"; then
    echo "  → Backend is ready!"
    break
  fi
  sleep 1
done

# Frontend
echo "  → Starting frontend on port 5200"
cd "$SCRIPT_DIR/frontend"
npx vite --host "$BIND_HOST" --port 5200 &
FRONTEND_PID=$!

# Wait for frontend to be ready, then open Chrome
echo "  → Waiting for servers..."
for i in {1..30}; do
  if curl -s http://localhost:5200 > /dev/null 2>&1; then
    echo "  → Opening browser..."
    open http://localhost:5200
    break
  fi
  sleep 1
done

echo ""
echo "========================================="
echo "  GODFIN is running!"
echo "  Backend:  http://localhost:5100"
echo "  Frontend: http://localhost:5200"
if [ "$BIND_HOST" = "0.0.0.0" ] && [ -n "$LOCAL_IP" ]; then
    echo ""
    echo "  Network access (other devices):"
    echo "  Frontend: http://${LOCAL_IP}:5200"
fi
echo "========================================="
echo ""
echo "Press Ctrl+C to stop."

# Trap to kill both on exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM

wait
