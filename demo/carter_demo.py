# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""One camera at 30 Hz, one IMU at 300 Hz, and a main loop we own."""

import time
from pathlib import Path

from isaacsim import SimulationApp

PHYSICS_HZ = 300
CAMERA_HZ = 30
SPEED = 0.8  # m/s
RESOLUTION = (1280, 720)

app = SimulationApp({
    "open_usd": str(Path(__file__).with_name("scene.usda")),
    "headless": False,
    "multi_gpu": False,
    "renderer": "RaytracedLighting",
    "extra_args": [
        "--/exts/isaacsim.core.simulation_manager/default_engine=physx",
        "--/exts/isaacsim.physics.newton/auto_switch_on_startup=false",
        "--enable", "isaacsim.streaming.rtsp",
        "--enable", "isaacsim.sensors.experimental.rtx",
        "--enable", "isaacsim.sensors.experimental.physics",
    ],
})

# Isaac/Kit imports must follow SimulationApp creation.
import carb.settings
import omni.replicator.core as rep
import omni.timeline
import omni.usd
from isaacsim.core.experimental.prims import Articulation
from isaacsim.core.rendering_manager import RenderingManager
from isaacsim.core.simulation_manager import SimulationEvent, SimulationManager
from isaacsim.core.utils.viewports import set_camera_view
from isaacsim.sensors.experimental.physics import IMUSensor
from isaacsim.streaming.rtsp import RTSPStreamWriter
from isaacsim.streaming.rtsp.impl.render_var_utils import ensure_render_var_on_product
from pxr import Gf

# The scene already contains the robot, camera and IMU.
stage = omni.usd.get_context().get_stage()
robot = Articulation("/World/Carter")
imu = IMUSensor("/World/Carter/chassis_link/IMU")
ground_offset = stage.GetPrimAtPath("/World/Ground/geom").GetAttribute("xformOp:translate")

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
wheel_indices = robot.get_dof_indices(["joint_wheel_left", "joint_wheel_right"])
set_camera_view(eye=[-4, -4, 3], target=[1, 0, 0.5])  # Set once; GUI navigation stays free.

last_report = time.monotonic()


def read_imu(dt, context):
    global last_report
    reading = imu.get_sensor_reading()  # Read every physics tick, including those between renders.
    now = time.monotonic()
    if now - last_report >= 5:
        print(f"IMU t={reading.time:.3f}s | acceleration=({reading.linear_acceleration_x:.3f}, "
              f"{reading.linear_acceleration_y:.3f}, {reading.linear_acceleration_z:.3f}) m/s²", flush=True)
        last_report = now


# Order 100 reads after the IMU backend has produced the current step's sample.
SimulationManager.register_callback(read_imu, event=SimulationEvent.PHYSICS_POST_STEP, order=100)
print("300 Hz physics + IMU, 30 Hz camera: rtsp://localhost:8554/stream", flush=True)
try:
    while app.is_running():
        started = time.monotonic()
        if timeline.is_playing():
            if SimulationManager.get_physics_simulation_view() is None:
                SimulationManager.initialize_physics()
            robot.set_dof_velocity_targets([[SPEED / 0.14, SPEED / 0.14]], dof_indices=wheel_indices)
            SimulationManager.step(steps=PHYSICS_HZ // CAMERA_HZ)  # 10 physics ticks; no rendering.
            position = robot.get_world_poses()[0].numpy()[0]
            ground_offset.Set(Gf.Vec3d(float(position[0] // 2 * 2), float(position[1] // 2 * 2), 0))
        RenderingManager.render()  # One render; also services GUI input.
        time.sleep(max(0, 1 / CAMERA_HZ - (time.monotonic() - started)))  # Wall-clock pacing.
except KeyboardInterrupt:
    pass
writer.detach()
app.close()
