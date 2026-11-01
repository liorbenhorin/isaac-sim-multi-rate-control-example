#!/usr/bin/env bash
set -euo pipefail
DEMO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
"$DEMO_ROOT/scripts/pixi.sh" install --locked --manifest-path "$DEMO_ROOT/pixi.toml"
for element in rtspsrc rtph264depay h264parse avdec_h264 videoconvert autovideosink fpsdisplaysink; do
    "$DEMO_ROOT/scripts/pixi.sh" run --locked --manifest-path "$DEMO_ROOT/pixi.toml" \
        gst-inspect-1.0 --exists "$element"
    echo "[Viewer] Available: $element"
done
"$DEMO_ROOT/scripts/pixi.sh" run --locked --manifest-path "$DEMO_ROOT/pixi.toml" \
    python -c 'import gi; gi.require_version("Gst", "1.0"); from gi.repository import Gst; Gst.init(None); print("[Viewer] Python GStreamer bindings available")'
