"""Validate a continuous demo run using only the Python standard library."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path)
    parser.add_argument("imu_csv", type=Path)
    parser.add_argument("--physics-hz", type=float, default=300)
    parser.add_argument("--camera-hz", type=float, default=30)
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text())
    with args.imu_csv.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if summary["error"]:
        raise SystemExit(f"Simulation failed: {summary['error']}")
    if len(rows) < 2 or len(rows) != summary["imu_samples"] or len(rows) != summary["physics_steps"]:
        raise SystemExit("Expected one valid IMU sample per physics step")
    if not all(math.isfinite(float(value)) for row in rows for value in row.values()):
        raise SystemExit("Non-finite IMU sample")
    timestamps = [float(row["sim_time_s"]) for row in rows]
    deltas = [b - a for a, b in zip(timestamps, timestamps[1:])]
    if not all(math.isclose(dt, 1 / args.physics_hz, rel_tol=0.01) for dt in deltas):
        raise SystemExit("IMU timestamps are not spaced at the requested physics rate (or Stop/Play occurred)")
    ratio = args.physics_hz / args.camera_hz
    if not math.isclose(ratio, round(ratio)) or set(summary["physics_steps_per_render"]) != {str(round(ratio))}:
        raise SystemExit("Unexpected physics steps per render")
    if summary["encoded_frames"] <= 0 or summary["position_m"][0] <= 0:
        raise SystemExit("Expected encoded camera frames and forward robot motion")
    print(
        f"PASS: {len(rows)} IMU samples, {1 / args.physics_hz:.6f}s spacing, "
        f"{round(ratio)} physics steps/render, {summary['encoded_frames']} encoded frames, "
        f"x={summary['position_m'][0]:.2f}m"
    )


if __name__ == "__main__":
    main()
