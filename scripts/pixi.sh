#!/usr/bin/env bash
set -euo pipefail
if command -v pixi >/dev/null 2>&1; then
    exec pixi "$@"
else
    exec "$(dirname -- "$0")/../../IsaacSim/.cache/pixi/0.77.1/linux-x86_64/pixi" "$@"
fi
