#!/bin/bash

# Script to run the Ghost MCP Server

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Install dependencies if needed
if [ ! -d ".venv" ]; then
    echo "Installing dependencies..."
    uv sync --all-extras
fi

# Run the server
echo "Starting Contraption Company MCP..."
uv run python -m src.main