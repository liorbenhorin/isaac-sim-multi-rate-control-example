# Multi-rate Carter with ROS 2

A minimal standalone Isaac Sim 6.2 demo with 300 Hz physics, a 30 Hz fisheye RTSP camera, 10 Hz 3D and 2D lidars publishing to ROS 2, and ROS 2 gamepad control. The launchers target the existing Isaac Sim pip environment and system ROS 2 Humble on Brev at `~/robotics/multi-rate-control`.

## Update

GitHub is the shared source: [isaac-sim-multi-rate-control-example](https://github.com/liorbenhorin/isaac-sim-multi-rate-control-example). Push changes from the development PC; pull on Brev before restarting the demo:

```bash
cd ~/robotics/multi-rate-control
git pull --ff-only
```

Simulation and ROS tests can run locally or on Brev. `scripts/generate_track.py` runs with standard Python.

## Run locally

The local launcher uses the source-built Isaac Sim in the adjacent `../IsaacSim` directory, including its Ubuntu 26.04 compatibility libraries. ROS tools and the controller use a separate [RoboStack](https://robostack.github.io/GettingStarted.html) Humble environment managed by Pixi:

```bash
./scripts/pixi.sh install --locked -e ros2
```

Run these in separate terminals, from this repository:

```bash
./run-local.sh --no-window
./scripts/pixi.sh run --locked -e ros2 control
./view.sh
```

The local controller reads the USB DualSense directly at `/dev/input/js0` and uses the same left-stick mapping. It does not need Selkies forwarding. The existing `control.sh` remains the Brev launcher.

ROS debugging commands:

```bash
./scripts/pixi.sh run --locked -e ros2 ros2 topic list
./scripts/pixi.sh run --locked -e ros2 ros2 topic hz /cmd_vel
./scripts/pixi.sh run --locked -e ros2 ros2 topic echo /cmd_vel --once
```

For an interactive ROS shell, use `./scripts/pixi.sh shell -e ros2`. Launch Isaac from a separate clean terminal: it uses its bundled Python/ROS libraries; the Pixi environment communicates with it over DDS. Both use Humble and `rmw_fastrtps_cpp`. If setting `ROS_DOMAIN_ID`, use the same value in both terminals.

## Run on Brev

Open separate terminals on the Brev desktop, each in `~/robotics/multi-rate-control`:

```bash
./run.sh       # Isaac Sim: 300 Hz physics, 30 Hz camera, 10 Hz lidar
./control.sh   # ROS 2 gamepad controller
./view.sh      # RTSP viewer
./view-lidar.sh # RViz point-cloud and robot TF viewer
```

Run each command in its own terminal. `./run.sh --no-window` runs Isaac without a GUI. The controller uses the installed system ROS 2 Humble/Python 3.10; Isaac uses its bundled Humble bridge with Python 3.12. Neither script requires sourcing ROS in the parent terminal.

Carter starts stationary. Connect your gamepad through the Brev desktop's joystick forwarding, then run `./control.sh` (either on the desktop or over SSH). Isaac can stay headless. The launcher sets the Selkies runtime directory and input interposer so Python can read `/dev/input/js0`; no additional gamepad packages are needed.

- **Left stick up/down:** forward/reverse, up to Carter's shipped 1 m/s; steering does not reduce the throttle command.
- **Left stick left/right:** turn in place at up to 1.2 rad/s with zero throttle. The turn-rate limit decreases linearly with absolute throttle demand: 0.7 rad/s at half throttle and 0.2 rad/s at full throttle (a commanded 5 m minimum radius at 1 m/s). Steering is softer near center. Left always commands positive yaw, including in reverse. No enable button is required.
- **Center the stick:** stop. A 10% dead zone ignores stick drift.
- **Ctrl+C:** send a stop command and exit.

Selkies presents the DualSense as a Microsoft Xbox 360 pad: left-stick axes 0/1; buttons are unused. The gamepad mappings and command limits are in `demo/ros_control.py`; the shipped differential controller retains its 1 m/s linear speed limit. Commands publish at 20 Hz.

This is a custom joystick response curve based on throttle demand, not measured vehicle speed. Isaac’s shipped differential-drive graph still converts `/cmd_vel` to wheel velocities and applies its acceleration limits.

The controller stops on joystick read errors or end-of-stream. Desktop/browser disconnect behavior depends on Selkies forwarding release events; joystick silence alone is not a disconnect signal because a held stick need not emit new events.

## How it works

`demo/scene.usda` selects Carter's shipped `ROS="Enabled"` and `Sensors="All_Sensors"` variants, then deactivates the stock cameras and IMU. The Hesai XT-32 3D lidar and front/rear SLAMTEC RPLIDAR S2E 2D lidars are enabled; the scene also contains our fisheye camera. Carter's odometry/TF graph publishes the robot frames, with its sensor targets restricted to the active lidars and camera. A clock publisher in the same graph publishes `/clock`.

The shipped differential-drive graph subscribes to **`/cmd_vel` (`geometry_msgs/Twist`)** and converts forward speed (`linear.x`) and yaw rate (`angular.z`) to wheel commands. It processes commands on each render/app update; physics integrates those commands at 300 Hz.

`demo/carter_demo.py` creates/configures physics, runs ten physics ticks per render, and streams the camera using Isaac's RTSP writer. `demo/ros_control.py` is the separate ROS gamepad controller. Physics configuration stays in Python; static scene and bridge wiring stay in USD. The 300/30 Hz rates are in simulation time; wall-clock sleep targets real time, but computation can make the simulator run slower.

The RTSP camera uses a native OpenCV fisheye projection (approximately 159° horizontal field of view). It sits 1 m behind and 1.3 m above the chassis origin, tilted 30° downward, so Carter and the track ahead are visible together. Lens intrinsics are authored for 1280 × 720 in `demo/scene.usda`. The camera follows the chassis through its USD parent transform.

### Lidar in RViz

The XT-32 uses Carter's stock mount and ROS graph to publish **`/front_3d_lidar/points` (`sensor_msgs/msg/PointCloud2`)**, with frame ID `front_3d_lidar`. Its sensor tick rate and scan rate are both 10 Hz in simulation time, with full-scan accumulation enabled. The camera still renders at 30 Hz and physics runs at 300 Hz.

The front and rear RPLIDAR S2E sensors use their stock mounts and ROS graphs to publish full 360-degree **`sensor_msgs/msg/LaserScan`** messages at 10 Hz in simulation time:

| Sensor | Topic | TF frame | RViz color |
| --- | --- | --- | --- |
| Front 2D lidar | `/front_2d_lidar/scan` | `front_2d_lidar` | Cyan |
| Rear 2D lidar | `/rear_2d_lidar/scan` | `rear_2d_lidar` | Magenta |

Both scan frames attach to `chassis_link`; the rear mount retains its 180-degree rotation. The saved RViz configuration enables both LaserScan displays alongside the 3D cloud. Toggle individual displays to compare the sensors.

Run `./view-lidar.sh` on the Brev desktop while the simulator is running. It sources system ROS 2 Humble and opens `demo/lidar.rviz`, with the lidar topics, Best Effort QoS, height coloring for the 3D cloud, and a **Robot TF** display with labeled axes and arrows. RViz uses simulation time from `/clock`, the fixed frame `odom`, and a view centered on `base_link`. The TF tree includes `odom → base_link → chassis_link`, the wheels/casters, `front_3d_lidar`, `front_2d_lidar`, `rear_2d_lidar`, and `chase_camera`. It shows the latest scans, not an accumulated world map. RViz is already installed on the current Brev instance; elsewhere, install `ros-humble-rviz2` and source your ROS 2 environment before launching. Extra RViz arguments are forwarded by the script.

Restart the simulator and RViz after changing the scene or viewer configuration. With lidar motion compensation enabled, RTX pipeline compilation can take about two minutes during startup before camera and ROS topics become available.

To inspect the publisher on Brev:

```bash
source /opt/ros/humble/setup.bash
ros2 topic info /front_3d_lidar/points --verbose
ros2 topic hz /front_3d_lidar/points
ros2 topic hz /front_2d_lidar/scan
ros2 topic hz /rear_2d_lidar/scan
```

RViz needs a graphical desktop even when Isaac runs with `--no-window`. Run the viewer inside the Brev desktop for remote use; the RTSP SSH tunnel below does not carry ROS 2/DDS traffic. If setting `ROS_DOMAIN_ID`, use the same value for the simulator and viewer.

The GUI viewpoint remains freely navigable. The RTSP viewer reports FPS/jitter every five seconds. To view the remote camera locally, keep this tunnel open and use the original local viewer:

```bash
ssh -N -L 8555:localhost:8554 nvidia-accelerated-desktop---robotics-a223e8
./view.sh rtsp://localhost:8555/stream
```

The first launch downloads the referenced Carter asset. `demo/track.usda` is a fixed, untextured 20 × 16 m circuit with a 2.4 m lane and continuous red/white barriers, 0.8 m high and 0.22 m thick. The floor and both continuous wall meshes have static collision geometry. Wall sections share vertices, with red/white materials assigned per face, so there are no overlapping box faces at the joins. Curves use 24 segments per quarter turn and smooth side normals. To regenerate the static asset, run `python3 scripts/generate_track.py`; the simulator simply loads the USD. Carter starts on the straight facing the checkerboard; holding forward eventually drives it into a barrier. The main loop no longer reads the robot pose or moves the ground.
