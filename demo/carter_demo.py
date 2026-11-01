# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Drive a sensor-light Nova Carter with ten physics/IMU ticks per camera frame.

Run with ``./run.sh``. The standalone entry point creates SimulationApp;
this module owns an explicit, synchronous physics/render loop on the main thread.
"""

from __future__ import annotations

import csv
import json
import math
import time
import traceback
from collections import Counter
from pathlib import Path
from typing import Any

import carb
import carb.settings
import numpy as np
import omni.kit.app
import omni.replicator.core as rep
import omni.timeline
import omni.usd
from isaacsim.core.experimental.prims import Articulation
from isaacsim.core.rendering_manager import RenderingManager
from isaacsim.core.simulation_manager import SimulationEvent, SimulationManager
from isaacsim.core.utils.viewports import set_camera_view
from isaacsim.sensors.experimental.physics import IMU, IMUSensor
from isaacsim.sensors.experimental.rtx import RtxCamera
from isaacsim.streaming.rtsp import RTSPStreamWriter
from isaacsim.streaming.rtsp.impl.render_var_utils import ensure_render_var_on_product
from pxr import Gf, PhysicsSchemaTools, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade


def read_config() -> dict[str, Any]:
    """Read launcher settings and reject inconsistent stepping rates."""
    config = dict(
        physicsHz=300,
        cameraHz=30,
        speed=0.8,
        width=1280,
        height=720,
        port=8554,
        mountPath="/stream",
        duration=0,
        imuCsv="",
        summary="",
        follow=False,
    )
    settings = carb.settings.get_settings()
    for key in config:
        value = settings.get(f"/carterDemo/{key}")
        if value is not None:
            config[key] = value
    for key in ("physicsHz", "cameraHz", "speed", "duration"):
        config[key] = float(config[key])
        if not math.isfinite(config[key]) or config[key] < 0:
            raise ValueError(f"{key} must be finite and nonnegative")
    if min(config["physicsHz"], config["cameraHz"]) <= 0:
        raise ValueError("Physics and camera rates must be positive")
    ratio = config["physicsHz"] / config["cameraHz"]
    if ratio < 1 or not math.isclose(ratio, round(ratio)) or not config["physicsHz"].is_integer():
        raise ValueError("physicsHz must be an integer and an integer multiple of cameraHz")
    for key in ("width", "height", "port"):
        config[key] = int(config[key])
    if any(config[key] <= 0 or config[key] % 2 for key in ("width", "height")):
        raise ValueError("Image dimensions must be positive and even")
    if not 1 <= config["port"] <= 65535 or not str(config["mountPath"]).startswith("/"):
        raise ValueError("Invalid RTSP port or mount path")
    return config


def make_material(stage: Usd.Stage, name: str, color: tuple[float, float, float]) -> UsdShade.Material:
    """Create a local diffuse material without external textures."""
    material = UsdShade.Material.Define(stage, f"/World/Materials/{name}")
    shader = UsdShade.Shader.Define(stage, f"{material.GetPath()}/Shader")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.85)
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return material


class CountedRTSPWriter(RTSPStreamWriter):
    """Use the shipped writer unchanged for transport; count nonempty encoded frames."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(
            port=config["port"],
            mountPath=config["mountPath"],
            width=config["width"],
            height=config["height"],
            encoding="h264",
        )
        self.encoded_frames = 0

    def write(self, data: dict) -> None:
        super().write(data)
        if any(key.startswith("LdrColor") and getattr(value, "size", 0) > 0 for key, value in data.items()):
            self.encoded_frames += 1


class CarterDemo:
    """Own the robot, sensor callbacks, stream, and bounded runtime statistics."""

    def __init__(self, simulation_app: Any) -> None:
        self.simulation_app = simulation_app
        self.config = read_config()
        self.app = omni.kit.app.get_app()
        self.timeline = omni.timeline.get_timeline_interface()
        self.callbacks = []
        self.writer = None
        self.render_product = None
        self.csv_file = None
        self.csv_writer = None
        self.physics_steps = 0
        self.sim_time = 0.0
        self.imu_samples = 0
        self.imu_last_time = None
        self.imu_dt_min = float("inf")
        self.imu_dt_max = 0.0
        self.imu_latest = None
        self.step_batches = Counter()
        self.robot = None
        self.wheel_indices = None
        self.position = np.zeros(3)
        self.ground_cell = None
        self.error = None
        self.started_wall = 0.0
        self.drive_time = 0.0
        self.stream_attached = False

    def setup(self) -> None:
        """Compose the light asset before playback and attach exactly two sensors."""
        self.timeline.stop()
        omni.usd.get_context().new_stage()
        stage = omni.usd.get_context().get_stage()
        world = UsdGeom.Xform.Define(stage, "/World")
        stage.SetDefaultPrim(world.GetPrim())
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        UsdPhysics.Scene.Define(stage, "/World/PhysicsScene")
        SimulationManager.switch_physics_engine("physx")

        robot_prim = stage.DefinePrim("/World/Carter", "Xform")
        robot_prim.GetReferences().AddReference(str(Path(__file__).with_name("nova_carter_light.usda")))
        while omni.usd.get_context().get_stage_loading_status()[2] > 0:
            self.app.update()
        chassis = stage.GetPrimAtPath("/World/Carter/chassis_link")
        if not chassis or not chassis.HasAPI(UsdPhysics.RigidBodyAPI):
            raise RuntimeError("Nova Carter asset did not load; check asset-server connectivity")
        stock_sensors = [
            p
            for p in Usd.PrimRange(robot_prim)
            if p.GetTypeName() in ("Camera", "OmniLidar", "OmniRadar", "IsaacImuSensor")
        ]
        if stock_sensors:
            raise RuntimeError(
                f"Sensors=None left unexpected sensor prims: {[str(p.GetPath()) for p in stock_sensors]}"
            )
        self.robot = Articulation("/World/Carter", positions=[[0, 0, 0.025]])

        # An actual infinite collision plane. Only its finite visual mesh follows the robot.
        PhysicsSchemaTools.addGroundPlane(stage, "/World/Ground", "Z", 2000.0, Gf.Vec3f(0), Gf.Vec3f(0.26, 0.3, 0.35))
        ground = stage.GetPrimAtPath("/World/Ground")
        ground_mat = make_material(stage, "Ground", (0.26, 0.3, 0.35))
        for prim in ground.GetChildren():
            if prim.IsA(UsdGeom.Mesh):
                UsdShade.MaterialBindingAPI.Apply(prim).Bind(ground_mat)
                self.ground_visual_op = UsdGeom.Xformable(prim).AddTranslateOp(opSuffix="follow")

        # Recycled visual-only grid: constant prim count, no additional collision geometry.
        grid = UsdGeom.Xform.Define(stage, "/World/Grid")
        self.grid_op = grid.AddTranslateOp()
        grid_mat = make_material(stage, "Grid", (0.65, 0.7, 0.76))
        for axis in range(2):
            for index in range(-30, 31):
                strip = UsdGeom.Cube.Define(stage, f"/World/Grid/Line{axis}_{index + 30}")
                strip.CreateSizeAttr(1.0)
                strip.AddTranslateOp().Set(
                    Gf.Vec3d(index * 2 if axis == 0 else 0, index * 2 if axis == 1 else 0, 0.001)
                )
                strip.AddScaleOp().Set(Gf.Vec3f(0.025 if axis == 0 else 120, 0.025 if axis == 1 else 120, 0.001))
                UsdShade.MaterialBindingAPI.Apply(strip.GetPrim()).Bind(grid_mat)
        UsdLux.DomeLight.Define(stage, "/World/Dome").CreateIntensityAttr(600)
        sun = UsdLux.DistantLight.Define(stage, "/World/Sun")
        sun.CreateIntensityAttr(1800)
        sun.AddRotateXYZOp().Set(Gf.Vec3f(-25, -35, 0))

        camera_path = "/World/Carter/chassis_link/FrontCamera"
        self.camera = RtxCamera(camera_path, tick_rate=self.config["cameraHz"])
        camera = UsdGeom.Camera(stage.GetPrimAtPath(camera_path))
        camera.CreateFocalLengthAttr(24)
        camera.CreateHorizontalApertureAttr(36)
        camera.CreateVerticalApertureAttr(36 * self.config["height"] / self.config["width"])
        camera.CreateClippingRangeAttr(Gf.Vec2f(0.05, 500))
        xform = UsdGeom.Xformable(camera)
        xform.ClearXformOpOrder()
        xform.AddTransformOp().Set(
            Gf.Matrix4d().SetLookAt(Gf.Vec3d(0.32, 0, 1.1), Gf.Vec3d(10, 0, 0.5), Gf.Vec3d(0, 0, 1)).GetInverse()
        )
        self.imu = IMUSensor(
            IMU.create(
                "/World/Carter/chassis_link/IMU",
                translations=[[0, 0, 0.2]],
                linear_acceleration_filter_size=1,
                angular_velocity_filter_size=1,
                orientation_filter_size=1,
            )
        )

        # The main loop explicitly steps physics; app updates must never add automatic steps.
        settings = carb.settings.get_settings()
        # Hide the editor's oversized camera glyph in the following viewport.
        settings.set("/app/viewport/show/camera", False)
        settings.set("/app/player/playSimulations", False)
        settings.set("/app/runLoops/main/rateLimitEnabled", False)
        SimulationManager.setup_simulation(dt=1.0 / self.config["physicsHz"], device="cpu")
        RenderingManager.set_dt(1.0 / self.config["cameraHz"])
        self.timeline.set_ticks_per_frame(1)
        self.timeline.set_looping(False)
        self.timeline.set_end_time(1e9)

        self.render_product = rep.create.render_product(
            camera_path, (self.config["width"], self.config["height"]), name="CarterFront", force_new=True
        )
        success, _ = ensure_render_var_on_product(stage, self.render_product.path, "LdrColor", "h264")
        if not success:
            raise RuntimeError("Could not configure the camera H.264 render variable")
        self.writer = CountedRTSPWriter(self.config)
        self.writer.attach([self.render_product.path])
        self.stream_attached = True

        if self.config["imuCsv"]:
            path = Path(self.config["imuCsv"]).expanduser().resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            self.csv_file = path.open("w", newline="")
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow(
                [
                    "physics_step",
                    "sim_time_s",
                    "ax_m_s2",
                    "ay_m_s2",
                    "az_m_s2",
                    "gx_rad_s",
                    "gy_rad_s",
                    "gz_rad_s",
                    "qw",
                    "qx",
                    "qy",
                    "qz",
                ]
            )
            print(f"[Carter] IMU CSV: {path}", flush=True)
        self.callbacks.append(
            SimulationManager.register_callback(self.pre_physics, event=SimulationEvent.PHYSICS_PRE_STEP)
        )
        # The shipped IMU backend updates at post-step order 1; read after it at order 100.
        self.callbacks.append(
            SimulationManager.register_callback(self.post_physics, event=SimulationEvent.PHYSICS_POST_STEP, order=100)
        )
        self.callbacks.append(
            SimulationManager.register_callback(self.on_stop, event=SimulationEvent.SIMULATION_STOPPED)
        )
        self.timeline.play()
        self.timeline.commit()
        SimulationManager.initialize_physics()
        self.started_wall = time.monotonic()
        set_camera_view(eye=[-4, -4, 3], target=[1, 0, 0.5])
        print(
            f"[Carter] Sensors=None variant, 1 camera + 1 IMU; physics={self.config['physicsHz']:g} Hz, "
            f"camera={self.config['cameraHz']:g} Hz; rtsp://localhost:{self.config['port']}"
            f"{self.config['mountPath']}",
            flush=True,
        )

    def pre_physics(self, dt: float, context: Any) -> None:
        """Ramp wheel drive targets after settling; move through wheel-ground contact."""
        try:
            if self.wheel_indices is None:
                self.wheel_indices = self.robot.get_dof_indices(["joint_wheel_left", "joint_wheel_right"])
            speed = self.config["speed"] * min(1.0, max(0.0, (self.drive_time - 1.0) / 2.0))
            self.robot.set_dof_velocity_targets([[speed / 0.14, speed / 0.14]], dof_indices=self.wheel_indices)
        except Exception:
            self.error = traceback.format_exc()

    def post_physics(self, dt: float, context: Any) -> None:
        """Read every fresh IMU sample, including steps between camera frames."""
        try:
            self.physics_steps += 1
            self.sim_time += dt
            self.drive_time += dt
            reading = self.imu.get_sensor_reading()
            if not reading.is_valid:
                return
            timestamp = float(reading.time)
            if self.imu_last_time is not None:
                delta = timestamp - self.imu_last_time
                if delta <= 0:
                    return
                self.imu_dt_min = min(self.imu_dt_min, delta)
                self.imu_dt_max = max(self.imu_dt_max, delta)
            self.imu_last_time = timestamp
            self.imu_samples += 1
            self.imu_latest = (
                self.physics_steps,
                timestamp,
                reading.linear_acceleration_x,
                reading.linear_acceleration_y,
                reading.linear_acceleration_z,
                reading.angular_velocity_x,
                reading.angular_velocity_y,
                reading.angular_velocity_z,
                reading.orientation_w,
                reading.orientation_x,
                reading.orientation_y,
                reading.orientation_z,
            )
            if self.csv_writer:
                self.csv_writer.writerow(self.imu_latest)
        except Exception:
            self.error = traceback.format_exc()

    def on_stop(self, event: Any) -> None:
        """Release the RTSP port on Stop and prepare the sensor for the next Play."""
        self.drive_time = 0.0
        self.imu_last_time = None
        self.wheel_indices = None
        if self.stream_attached:
            self.writer.detach()
            self.stream_attached = False

    def update_view(self) -> None:
        """Recycle the visual grid and follow the simulated robot pose in the GUI."""
        if self.physics_steps == 0 or not self.timeline.is_playing():
            return
        positions, _ = self.robot.get_world_poses()
        self.position = positions.numpy()[0]
        x, y, z = map(float, self.position)
        cell = (math.floor(x / 2) * 2, math.floor(y / 2) * 2)
        if cell != self.ground_cell:
            self.grid_op.Set(Gf.Vec3d(*cell, 0))
            self.ground_visual_op.Set(Gf.Vec3d(*cell, 0))
            self.ground_cell = cell
        if self.config["follow"]:
            set_camera_view(eye=[x - 4, y - 4, z + 3], target=[x + 1, y, z + 0.5])

    def run(self) -> None:
        """Own the main thread: physics batch, one render, then optional wall-clock wait."""
        self.setup()
        steps_per_render = round(self.config["physicsHz"] / self.config["cameraHz"])
        render_period = 1.0 / self.config["cameraHz"]
        deadline = time.monotonic()
        last_wall = time.monotonic()
        last_steps = last_frames = last_samples = 0
        while self.simulation_app.is_running():
            if self.config["duration"] and time.monotonic() - self.started_wall >= self.config["duration"]:
                break
            if self.error:
                raise RuntimeError(self.error)
            before = self.physics_steps
            if self.timeline.is_playing():
                # Stop/Play invalidates the physics view. Warm up before the next explicit batch.
                if SimulationManager.get_physics_simulation_view() is None:
                    SimulationManager.initialize_physics()
                if not self.stream_attached:
                    self.writer.attach([self.render_product.path])
                    self.stream_attached = True
                SimulationManager.step(steps=steps_per_render)
                self.step_batches[self.physics_steps - before] += 1
            self.update_view()
            before_render = self.physics_steps
            RenderingManager.render()  # Services GUI input and renders without advancing physics.
            if self.physics_steps != before_render:
                raise RuntimeError("Render unexpectedly advanced physics")
            if self.error:
                raise RuntimeError(self.error)
            now = time.monotonic()
            if now - last_wall >= 1:
                elapsed = now - last_wall
                frames = self.writer.encoded_frames
                a = self.imu_latest[2:5] if self.imu_latest else (0, 0, 0)
                print(
                    f"[Carter] sim={self.sim_time:.2f}s x={self.position[0]:.2f}m | "
                    f"wall rates: physics={(self.physics_steps-last_steps)/elapsed:.1f} Hz "
                    f"IMU={(self.imu_samples-last_samples)/elapsed:.1f} Hz "
                    f"camera={(frames-last_frames)/elapsed:.1f} fps | "
                    f"accel=({a[0]:.3f}, {a[1]:.3f}, {a[2]:.3f}) m/s^2",
                    flush=True,
                )
                last_wall, last_steps, last_frames, last_samples = now, self.physics_steps, frames, self.imu_samples
                if self.csv_file:
                    self.csv_file.flush()
            # Pace wall time independently of fixed simulation dt. Do not burst to catch up after a stall.
            deadline += render_period
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
            else:
                deadline = time.monotonic()

    def close(self) -> None:
        """Save run statistics and release the server and callback subscriptions."""
        summary = dict(
            physics_steps=self.physics_steps,
            simulation_seconds=self.sim_time,
            imu_samples=self.imu_samples,
            imu_dt_min=self.imu_dt_min if self.imu_samples > 1 else None,
            imu_dt_max=self.imu_dt_max,
            physics_steps_per_render=dict(self.step_batches),
            encoded_frames=self.writer.encoded_frames if self.writer else 0,
            position_m=self.position.tolist(),
            error=self.error,
        )
        print(f"[Carter] Summary: {json.dumps(summary)}", flush=True)
        if self.config["summary"]:
            path = Path(self.config["summary"]).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(summary, indent=2) + "\n")
        for callback in self.callbacks:
            SimulationManager.deregister_callback(callback)
        self.callbacks.clear()
        if self.writer:
            self.writer.detach()
        self.timeline.stop()
        if self.csv_file:
            self.csv_file.close()
        if self.render_product:
            self.render_product.destroy()


def run_checked(simulation_app: Any) -> int:
    """Run synchronously and return a failing exit code on setup or callback errors."""
    demo = None
    result = 0
    try:
        demo = CarterDemo(simulation_app)
        demo.run()
    except KeyboardInterrupt:
        pass
    except Exception:
        result = 1
        error = traceback.format_exc()
        if demo:
            demo.error = error
        carb.log_error(f"Carter demo failed:\n{error}")
    finally:
        if demo:
            demo.close()
    return result
