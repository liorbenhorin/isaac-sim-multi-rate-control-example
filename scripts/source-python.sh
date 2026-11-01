#!/usr/bin/env bash
# Supply the same host compatibility libraries as the existing source-build launcher.
set -euo pipefail
DEMO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_ROOT="${ISAACSIM_SOURCE_ROOT:-$DEMO_ROOT/../IsaacSim}"
APP_DIR="$SOURCE_ROOT/_build/linux-x86_64/release"
COMPAT_DIR="$SOURCE_ROOT/tools/runtime-compat"
if [[ ! -x "$APP_DIR/python.sh" ]]; then
    echo "Source-build Python launcher missing: $APP_DIR/python.sh" >&2
    exit 1
fi
"$DEMO_ROOT/scripts/pixi.sh" install --locked --manifest-path "$COMPAT_DIR/pixi.toml"
runtime_path="$COMPAT_DIR/.pixi/envs/default/lib"
nvidia_dir="$APP_DIR/exts/isaacsim.pip.nv/pip_prebundle/nvidia"
for library_dir in "$nvidia_dir"/*/lib; do
    [[ -d "$library_dir" ]] && runtime_path="$runtime_path:$library_dir"
done
export LD_LIBRARY_PATH="$runtime_path${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export LD_PRELOAD="$nvidia_dir/cuda_runtime/lib/libcudart.so.12${LD_PRELOAD:+:$LD_PRELOAD}"
exec "$APP_DIR/python.sh" --no-ros-env "$@"
