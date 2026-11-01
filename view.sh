#!/usr/bin/env bash
set -euo pipefail
DEMO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
    echo "Usage: ./view.sh [rtsp://localhost:8554/stream]"
    echo "Uses the locked Pixi GStreamer environment; a graphical display is required."
    exit 0
fi
if (( $# > 1 )); then
    echo "Expected at most one RTSP URL." >&2
    exit 2
fi
exec "$DEMO_ROOT/scripts/pixi.sh" run --locked --manifest-path "$DEMO_ROOT/pixi.toml" \
    gst-launch-1.0 rtspsrc location="${1:-rtsp://localhost:8554/stream}" protocols=tcp latency=100 \
    '!' rtph264depay '!' h264parse '!' avdec_h264 '!' videoconvert '!' autovideosink
