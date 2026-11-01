#!/usr/bin/env bash
set -eo pipefail
cd -- "$(dirname -- "$0")"
source /opt/ros/humble/setup.bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export DISPLAY="${DISPLAY:-:99}"
exec /usr/bin/python3 demo/ros_control.py
