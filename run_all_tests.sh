#!/bin/bash
set -e
PYTHONPATH=/root/sender/src
export PYTHONPATH
cd /root/sender
python3 -m pytest tests/unit/ -v --tb=short 2>&1
