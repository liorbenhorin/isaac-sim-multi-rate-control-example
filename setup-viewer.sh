#!/usr/bin/env bash
set -euo pipefail
DEMO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
"$DEMO_ROOT/scripts/pixi.sh" install --locked --manifest-path "$DEMO_ROOT/pixi.toml"
for element in rtspsrc rtph264depay h264parse avdec_h264 videoconvert autovideosink; do
    "$DEMO_ROOT/scripts/pixi.sh" run --locked --manifest-path "$DEMO_ROOT/pixi.toml" \
        gst-inspect-1.0 --exists "$element"
    echo "[Viewer] Available: $element"
done
