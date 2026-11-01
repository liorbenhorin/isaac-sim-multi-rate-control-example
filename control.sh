#!/usr/bin/env bash
set -eo pipefail
cd -- "$(dirname -- "$0")"
source /opt/ros/humble/setup.bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export XDG_RUNTIME_DIR=/tmp/selkies-runtime-ubuntu
export LD_PRELOAD=/opt/selkies/usr/lib/selkies_input_interposer.so
exec /usr/bin/python3 demo/ros_control.py
