#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ -x ../IsaacSim/_build/linux-x86_64/release/python.sh ]]; then
    exec ./scripts/source-python.sh demo/carter_demo.py "$@"
else
    exec "$HOME/robotics/isaacsim-6.2/.venv/bin/python" demo/carter_demo.py "$@"
fi
