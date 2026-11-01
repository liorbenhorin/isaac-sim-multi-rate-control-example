#!/usr/bin/env bash
set -euo pipefail
DEMO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$DEMO_ROOT/scripts/pixi.sh" run --locked --manifest-path "$DEMO_ROOT/pixi.toml" \
    python "$DEMO_ROOT/scripts/rtsp_viewer.py" "$@"
