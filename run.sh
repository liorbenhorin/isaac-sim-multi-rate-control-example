#!/usr/bin/env bash
set -euo pipefail
DEMO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
    cat <<'HELP'
Usage: ./run.sh [Isaac Sim arguments...]

Nova Carter: 300 Hz physics/IMU, 30 Hz H.264 RTSP camera, 0.8 m/s forward.
GUI navigation is free by default. Stream: rtsp://localhost:8554/stream.

  ./run.sh
  ./run.sh --/carterDemo/follow=true
  ./run.sh --no-window --/carterDemo/duration=30
  ./run.sh --/carterDemo/imuCsv=outputs/imu.csv --/carterDemo/summary=outputs/summary.json

Standalone Python; this script creates SimulationApp and owns the main loop.
Runtime detection: ../IsaacSim source build, then ~/robotics/isaacsim-6.2/.venv.
Override with ISAACSIM_SOURCE_ROOT=/path/to/source or ISAACSIM_VENV=/path/to/venv.
ISAACSIM_PYTHON=/path/to/python-launcher also accepts a configured Python executable.
Settings under /carterDemo/: physicsHz=300, cameraHz=30, speed=0.8,
width=1280, height=720, port=8554, mountPath=/stream, duration=0,
imuCsv="", summary="", follow=false. Duration uses wall-clock seconds after setup.
HELP
    exit 0
fi

if [[ "${PYTHONPATH:-}:${AMENT_PREFIX_PATH:-}" == *"/opt/ros/"* ]]; then
    echo "Launch in a fresh terminal without sourcing system ROS; Isaac uses Python 3.12." >&2
    exit 1
fi

launcher=()
if [[ -n "${ISAACSIM_PYTHON:-}" ]]; then
    launcher=("$ISAACSIM_PYTHON")
elif [[ -n "${ISAACSIM_VENV:-}" ]]; then
    launcher=("$ISAACSIM_VENV/bin/python")
elif [[ -n "${ISAACSIM_SOURCE_ROOT:-}" || -x "$DEMO_ROOT/../IsaacSim/_build/linux-x86_64/release/python.sh" ]]; then
    launcher=("$DEMO_ROOT/scripts/source-python.sh")
elif [[ -x "$HOME/robotics/isaacsim-6.2/.venv/bin/python" ]]; then
    launcher=("$HOME/robotics/isaacsim-6.2/.venv/bin/python")
else
    echo "Isaac Sim not found. Set ISAACSIM_VENV or ISAACSIM_SOURCE_ROOT (see --help)." >&2
    exit 1
fi
if [[ ! -x "${launcher[0]}" ]]; then
    echo "Isaac Sim launcher is not executable: ${launcher[0]}" >&2
    exit 1
fi

export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1
echo "[Demo] Runtime: ${launcher[0]}"
exec "${launcher[@]}" "$DEMO_ROOT/demo/main.py" \
    --/isaac/startup/ros_bridge_extension= \
    --enable isaacsim.streaming.rtsp \
    --enable isaacsim.sensors.experimental.rtx \
    --enable isaacsim.sensors.experimental.physics \
    --/exts/isaacsim.core.simulation_manager/default_engine=physx \
    --/exts/isaacsim.physics.newton/auto_switch_on_startup=false \
    --/app/settings/persistent=false \
    --/app/file/ignoreUnsavedStage=true \
    --/app/asyncRendering=false \
    --/exts/isaacsim.core.throttling/enable_async=false \
    --/app/player/useFixedTimeStepping=true \
    --/app/runLoops/main/rateLimitEnabled=false \
    --/app/player/playSimulations=false \
    --/renderer/multiGpu/enabled=false \
    --/rtx/rendermode=RayTracedLighting \
    "$@"
