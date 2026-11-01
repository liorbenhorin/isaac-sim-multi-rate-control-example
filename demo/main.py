"""Standalone entry point: create SimulationApp before importing any Kit-dependent code."""

from __future__ import annotations

import sys


def main() -> int:
    from isaacsim import SimulationApp

    simulation_app = SimulationApp(
        {
            "headless": "--no-window" in sys.argv,
            "multi_gpu": False,
            "renderer": "RaytracedLighting",
            "fast_shutdown": True,
        }
    )
    result = 1
    try:
        from carter_demo import run_checked

        result = run_checked(simulation_app)
        return result
    finally:
        # Use Kit's default process shutdown after closing our writer, callbacks and CSV.
        # Preserve failures rather than letting fast shutdown turn them into exit status 0.
        simulation_app.close(exit_code=result)


if __name__ == "__main__":
    raise SystemExit(main())
