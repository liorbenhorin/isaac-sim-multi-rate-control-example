#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
app_dir="$(cd ../IsaacSim/_build/linux-x86_64/release && pwd)"
export ROS_DISTRO=humble RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export LD_LIBRARY_PATH="$app_dir/exts/isaacsim.ros2.core/humble/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec ./scripts/source-python.sh demo/carter_demo.py "$@"
