#!/bin/bash
# ClubMillies — Start all services
# Usage: ./scripts/start.sh

set -e

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"

echo ""
echo "  ╔═════════════════════════════════════════════╗"
echo "  ║     ClubMillies — Starting Services         ║"
echo "  ╚═════════════════════════════════════════════╝"
echo ""

# Load .env if exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
    echo "  ✓ Loaded .env"
fi

# Install Python deps
echo "  → Installing Python dependencies..."
pip install -q -r requirements.txt 2>/dev/null

# Initialize database
echo "  → Initializing database..."
python3 -c "
from core.database import init_db_sync
init_db_sync()
print('  ✓ Database ready')
"

# Install dashboard deps if needed
if [ -d dashboard ] && [ ! -d dashboard/node_modules ]; then
    echo "  → Installing dashboard dependencies..."
    cd dashboard && npm install --silent 2>/dev/null && cd ..
fi

# Start backend (API + Trading Engine + Telegram)
echo "  → Starting backend..."
python3 main.py &
BACKEND_PID=$!

# Start dashboard
if [ -d dashboard/node_modules ]; then
    echo "  → Starting dashboard..."
    cd dashboard && npm run dev &
    DASHBOARD_PID=$!
    cd ..
fi

echo ""
echo "  ╔═════════════════════════════════════════════╗"
echo "  ║     ClubMillies is LIVE                     ║"
echo "  ║                                             ║"
echo "  ║     API:       http://localhost:8000         ║"
echo "  ║     Dashboard: http://localhost:3000         ║"
echo "  ║                                             ║"
echo "  ║     Press Ctrl+C to stop                    ║"
echo "  ╚═════════════════════════════════════════════╝"
echo ""

# Wait for interrupt
trap "echo '  Shutting down...'; kill $BACKEND_PID $DASHBOARD_PID 2>/dev/null; exit 0" SIGINT SIGTERM
wait
