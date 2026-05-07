#!/bin/bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$BASE_DIR"

source venv/bin/activate

# Allow passing arguments to agent.py (e.g. ./start_agent.sh --text)
exec python agent.py "$@"
