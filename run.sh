#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
venv="$HOME/robotics/isaacsim-6.2/.venv"
export ROS_DISTRO=humble RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export LD_LIBRARY_PATH="$venv/lib/python3.12/site-packages/isaacsim/exts/isaacsim.ros2.core/humble/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$venv/bin/python" demo/carter_demo.py "$@"
