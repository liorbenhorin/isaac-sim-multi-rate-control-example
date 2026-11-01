#!/usr/bin/env bash
# Local Ubuntu 26.04 compatibility libraries, also used by IsaacSim/run-local.sh.
set -euo pipefail
SOURCE_ROOT="$(cd -- "$(dirname -- "$0")/../../IsaacSim" && pwd)"
APP_DIR="$SOURCE_ROOT/_build/linux-x86_64/release"
COMPAT_DIR="$SOURCE_ROOT/tools/runtime-compat"
"$(dirname -- "$0")/pixi.sh" install --locked --manifest-path "$COMPAT_DIR/pixi.toml"
runtime_path="$COMPAT_DIR/.pixi/envs/default/lib"
nvidia_dir="$APP_DIR/exts/isaacsim.pip.nv/pip_prebundle/nvidia"
for library_dir in "$nvidia_dir"/*/lib; do
    runtime_path="$runtime_path:$library_dir"
done
export LD_LIBRARY_PATH="$runtime_path${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export LD_PRELOAD="$nvidia_dir/cuda_runtime/lib/libcudart.so.12${LD_PRELOAD:+:$LD_PRELOAD}"
exec "$APP_DIR/python.sh" --no-ros-env "$@"
