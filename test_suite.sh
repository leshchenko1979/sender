#!/bin/bash
set -e

cd /root/sender

# Create venv if not exists
if [ ! -d .venv ]; then
    python3 -m venv .venv
fi

# Install deps
.venv/bin/pip install -q pytest croniter pydantic gspread pyyaml 2>&1

# Run tests
PYTHONPATH=/root/sender/src .venv/bin/pytest tests/unit/ -v --tb=short 2>&1
