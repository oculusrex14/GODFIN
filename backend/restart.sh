#!/bin/bash
# Robust restart script for GODFIN backend
set -e

# Get script directory and backend directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR"
LOG_FILE="$BACKEND_DIR/logs/restart.log"
PID_FILE="$BACKEND_DIR/.backend.pid"
PORT=5100

# Load user's PATH so uvicorn/npx/node/python3 are found when double-clicked
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/Library/Python/3.9/bin:$PATH"

# Ensure logs directory exists
mkdir -p "$BACKEND_DIR/logs"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "========================================="
log "  GODFIN Backend Restart"
log "========================================="

# Function to check if port is in use
is_port_in_use() {
    lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null 2>&1 || \
    netstat -an 2>/dev/null | grep -q ":$1.*LISTEN" || \
    ss -tuln 2>/dev/null | grep -q ":$1"
}

# Function to kill process using a port
kill_port_process() {
    local port=$1
    local pid

    # Try lsof first (macOS/Linux)
    pid=$(lsof -Pi :$port -sTCP:LISTEN -t 2>/dev/null | head -1)

    if [ -n "$pid" ]; then
        log "Killing process $pid using port $port"
        kill -TERM "$pid" 2>/dev/null || true
        sleep 2

        # Force kill if still running
        if kill -0 "$pid" 2>/dev/null; then
            log "Force killing process $pid"
            kill -9 "$pid" 2>/dev/null || true
            sleep 1
        fi
    fi
}

# Kill any process using the port
if is_port_in_use $PORT; then
    log "Port $PORT is in use, terminating existing process..."
    kill_port_process $PORT
fi

# Also check for existing uvicorn processes
UVICORN_PIDS=$(pgrep -f "uvicorn.*app.main:app" 2>/dev/null || true)
if [ -n "$UVICORN_PIDS" ]; then
    log "Found existing uvicorn processes: $UVICORN_PIDS"
    echo "$UVICORN_PIDS" | xargs kill -TERM 2>/dev/null || true
    sleep 2
    # Force kill any remaining
    echo "$UVICORN_PIDS" | xargs kill -9 2>/dev/null || true
fi

# Clear Python bytecode cache to ensure latest code is loaded
log "Clearing Python cache..."
find "$BACKEND_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$BACKEND_DIR" -name "*.pyc" -delete 2>/dev/null || true
find "$BACKEND_DIR" -name "*.pyo" -delete 2>/dev/null || true

# Wait for port to be released
log "Waiting for port $PORT to be released..."
for i in {1..10}; do
    if ! is_port_in_use $PORT; then
        log "Port $PORT is now free"
        break
    fi
    log "Waiting... ($i/10)"
    sleep 1
done

# Activate virtual environment
if [ -f "$BACKEND_DIR/venv/bin/activate" ]; then
    source "$BACKEND_DIR/venv/bin/activate"
else
    log "ERROR: Virtual environment not found at $BACKEND_DIR/venv"
    exit 1
fi

# Start uvicorn with proper logging - use full path to venv's uvicorn
log "Starting uvicorn on port $PORT..."
cd "$BACKEND_DIR"

# Start uvicorn - use full path to avoid PATH issues when called from API
BIND_HOST=$("$BACKEND_DIR/venv/bin/python" -m app.core.network_access)
exec "$BACKEND_DIR/venv/bin/uvicorn" app.main:app --host "$BIND_HOST" --port "$PORT" --log-level info
