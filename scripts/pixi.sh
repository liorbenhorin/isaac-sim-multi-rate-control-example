#!/usr/bin/env bash
# Resolve Pixi without activating the viewer environment in the simulator shell.
set -euo pipefail
DEMO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -n "${PIXI_BIN:-}" ]]; then
    exec "$PIXI_BIN" "$@"
elif command -v pixi >/dev/null 2>&1; then
    exec pixi "$@"
elif [[ -x "$HOME/.pixi/bin/pixi" ]]; then
    exec "$HOME/.pixi/bin/pixi" "$@"
fi
# Optional fallback for the existing local source checkout's cached Pixi.
for candidate in "$DEMO_ROOT/../IsaacSim/.cache/pixi/"*/linux-x86_64/pixi; do
    if [[ -x "$candidate" ]]; then
        exec "$candidate" "$@"
    fi
done
echo "Pixi not found. Install Pixi or set PIXI_BIN to its executable path." >&2
exit 1
