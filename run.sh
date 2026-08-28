#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
pkill -f "python.*main.py" 2>/dev/null || true
sleep 0.2
[ ! -d ".venv" ] && python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
python main.py
