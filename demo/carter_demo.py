# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""300 Hz physics, a 30 Hz camera, 10 Hz lidars, and a main loop we own."""

import time
from pathlib import Path

from isaacsim import SimulationApp

PHYSICS_HZ = 300
CAMERA_HZ = 30
RESOLUTION = (1280, 720)

app = SimulationApp({
    "open_usd": str(Path(__file__).with_name("scene.usda")),
    "headless": False,
    "multi_gpu": False,
    "enable_motion_bvh": True,  # Lidar motion compensation with multi-tick rendering.
    "renderer": "RaytracedLighting",
    "extra_args": [
        "--/exts/isaacsim.core.simulation_manager/default_engine=physx",
        "--/exts/isaacsim.physics.newton/auto_switch_on_startup=false",
        "--enable", "isaacsim.ros2.bridge",
        "--enable", "isaacsim.streaming.rtsp",
        "--enable", "isaacsim.sensors.experimental.rtx",
    ],
})

# Isaac/Kit imports must follow SimulationApp creation.
import carb.settings
import omni.replicator.core as rep
import omni.timeline
import omni.usd
from isaacsim.core.rendering_manager import RenderingManager
from isaacsim.core.simulation_manager import SimulationManager
from isaacsim.core.utils.viewports import set_camera_view
from isaacsim.streaming.rtsp import RTSPStreamWriter
from isaacsim.streaming.rtsp.impl.render_var_utils import ensure_render_var_on_product

# The scene contains the robot, camera, and lidars with their ROS publishers.
stage = omni.usd.get_context().get_stage()

# Explicit stepping: rendering/app updates must not advance physics automatically.
settings = carb.settings.get_settings()
settings.set("/app/player/playSimulations", False)
settings.set("/app/runLoops/main/rateLimitEnabled", False)
settings.set("/app/viewport/show/camera", False)
# Create the physics scene and configure its timestep in Python.
SimulationManager.setup_simulation(dt=1 / PHYSICS_HZ, device="cpu")
RenderingManager.set_dt(1 / CAMERA_HZ)
timeline = omni.timeline.get_timeline_interface()
timeline.set_looping(False)

# The shipped RTSP writer consumes this camera's H.264 render output.
render_product = rep.create.render_product("/World/Carter/chassis_link/FrontCamera", RESOLUTION)
ensure_render_var_on_product(stage, render_product.path, "LdrColor", "h264")
writer = RTSPStreamWriter(port=8554, mountPath="/stream", encoding="h264", width=RESOLUTION[0], height=RESOLUTION[1])
writer.attach([render_product.path])

timeline.play()
timeline.commit()
SimulationManager.initialize_physics()
set_camera_view(eye=[24, -22, 25], target=[8, 6, 0])  # Set once; GUI navigation stays free.

print("300 Hz physics, 30 Hz camera: rtsp://localhost:8554/stream", flush=True)
print("10 Hz XT-32 lidar: /front_3d_lidar/points (frame: front_3d_lidar)", flush=True)
print("10 Hz 2D lidars: /front_2d_lidar/scan and /rear_2d_lidar/scan", flush=True)
try:
    while app.is_running():
        started = time.monotonic()
        if timeline.is_playing():
            if SimulationManager.get_physics_simulation_view() is None:
                SimulationManager.initialize_physics()
            SimulationManager.step(steps=PHYSICS_HZ // CAMERA_HZ)  # 10 physics ticks; no rendering.
        RenderingManager.render()  # One render; also services GUI input.
        time.sleep(max(0, 1 / CAMERA_HZ - (time.monotonic() - started)))  # Wall-clock pacing.
except KeyboardInterrupt:
    pass
writer.detach()
app.close()
