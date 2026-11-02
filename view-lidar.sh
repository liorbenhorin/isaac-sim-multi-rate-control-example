#!/usr/bin/env bash
# Open 3D/2D lidar scans and robot TF in RViz on the machine's desktop.
set -eo pipefail
DEMO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ -f /opt/ros/humble/setup.bash ]; then
    source /opt/ros/humble/setup.bash
fi
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
if ! command -v rviz2 >/dev/null 2>&1; then
    echo "rviz2 is required. Install ros-humble-rviz2 and source your ROS 2 environment." >&2
    exit 1
fi
exec rviz2 -d "$DEMO_ROOT/demo/lidar.rviz" --ros-args -p use_sim_time:=true "$@"
