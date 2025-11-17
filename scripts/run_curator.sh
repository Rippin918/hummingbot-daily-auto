#!/bin/bash
# Launcher script for the Sapient HRM Liquidity Curator
# This script ensures the proper environment is activated and runs the curator

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🤖 Starting Sapient HRM Liquidity Curator for Linea Ignition"
echo "=================================================="

# Activate virtual environment if it exists
if [ -d "$PROJECT_DIR/venv" ]; then
    echo "✓ Activating virtual environment..."
    source "$PROJECT_DIR/venv/bin/activate"
elif [ -d "$PROJECT_DIR/.venv" ]; then
    echo "✓ Activating virtual environment..."
    source "$PROJECT_DIR/.venv/bin/activate"
else
    echo "⚠ No virtual environment found. Using system Python."
fi

# Check if required packages are installed
if ! python3 -c "import yaml" 2>/dev/null; then
    echo "⚠ Required packages not found. Installing dependencies..."
    pip install -r "$PROJECT_DIR/requirements.txt"
fi

# Create logs directory if it doesn't exist
mkdir -p "$PROJECT_DIR/logs"

# Run the curator with any passed arguments
echo "✓ Launching liquidity curator..."
python3 "$SCRIPT_DIR/liquidity_curator.py" "$@"
