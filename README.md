# Multi-rate Carter with ROS 2

A minimal standalone Isaac Sim 6.2 demo with 300 Hz physics/IMU, a 30 Hz fisheye RTSP camera, and ROS 2 gamepad control. The launchers target the existing Isaac Sim pip environment and system ROS 2 Humble on Brev at `~/robotics/multi-rate-control`.

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
./scripts/pixi.sh run --locked -e ros2 ros2 topic hz /chassis/imu
./scripts/pixi.sh run --locked -e ros2 ros2 topic echo /chassis/imu --once
```

For an interactive ROS shell, use `./scripts/pixi.sh shell -e ros2`. Launch Isaac from a separate clean terminal: it uses its bundled Python/ROS libraries; the Pixi environment communicates with it over DDS. Both use Humble and `rmw_fastrtps_cpp`. If setting `ROS_DOMAIN_ID`, use the same value in both terminals.

## Run on Brev

Open three terminals on Brev, each in `~/robotics/multi-rate-control`:

```bash
./run.sh       # Isaac Sim: 300 Hz physics/IMU, 30 Hz camera
./control.sh   # ROS 2 gamepad controller and IMU readout
./view.sh      # RTSP viewer
```

Run each command in its own terminal. `./run.sh --no-window` runs Isaac without a GUI. The controller uses the installed system ROS 2 Humble/Python 3.10; Isaac uses its bundled Humble bridge with Python 3.12. Neither script requires sourcing ROS in the parent terminal.

Carter starts stationary. Connect your gamepad through the Brev desktop's joystick forwarding, then run `./control.sh` (either on the desktop or over SSH). Isaac can stay headless. The launcher sets the Selkies runtime directory and input interposer so Python can read `/dev/input/js0`; no additional gamepad packages are needed.

- **Left stick up/down:** forward/reverse, up to 2 m/s when driving straight.
- **Left stick left/right:** steering controls turn radius, down to 2 m at full steering, with a softer response near center. Speed falls to at most 1 m/s at full steering. Turn rate follows forward/reverse speed: sideways stick alone does not spin the robot, and reverse steers like a car. No enable button is required.
- **Center the stick:** stop. A 10% dead zone ignores stick drift.
- **Ctrl+C:** send a stop command and exit.

Selkies presents the DualSense as a Microsoft Xbox 360 pad: left-stick axes 0/1; buttons are unused. The gamepad mappings and command limits are in `demo/ros_control.py`; `demo/scene.usda` also sets the shipped differential controller’s linear speed limit to 2 m/s. Commands publish at 20 Hz; IMU acceleration, yaw rate and received sample rate print every five seconds. The sample rate uses wall time, so it falls below 300 Hz when simulation runs slower than real time.

The controller stops on joystick read errors or end-of-stream. Desktop/browser disconnect behavior depends on Selkies forwarding release events; joystick silence alone is not a disconnect signal because a held stick need not emit new events.

## How it works

`demo/scene.usda` selects Carter's shipped `ROS="Enabled"` and `Sensors="None"` variants. The stock sensor branch and odometry/TF graph are disabled; the scene contains one camera and one IMU.

The shipped differential-drive graph subscribes to **`/cmd_vel` (`geometry_msgs/Twist`)** and converts forward speed (`linear.x`) and yaw rate (`angular.z`) to wheel commands. It processes commands on each render/app update; physics integrates those commands at 300 Hz.

The shipped IMU graph is retargeted to our sensor and publishes **`/chassis/imu` (`sensor_msgs/Imu`)**, with frame ID `carter_imu` and sensor simulation-time timestamps. Python triggers that graph after each physics tick, after the IMU backend updates. IMU reading and ROS message construction happen in the shipped graph nodes.

`demo/carter_demo.py` creates/configures physics, runs ten physics ticks per render, and streams the camera using Isaac's RTSP writer. `demo/ros_control.py` is the separate ROS controller/subscriber. Physics configuration stays in Python; static scene and bridge wiring stay in USD. The 300/30 Hz rates are in simulation time; wall-clock sleep targets real time, but computation can make the simulator run slower.

The RTSP camera uses a native OpenCV fisheye projection (approximately 159° horizontal field of view). It sits 1 m behind and 1.3 m above the chassis origin, tilted 30° downward, so Carter and the track ahead are visible together. Lens intrinsics are authored for 1280 × 720 in `demo/scene.usda`. The camera follows the chassis through its USD parent transform.

The GUI viewpoint remains freely navigable. The RTSP viewer reports FPS/jitter every five seconds. To view the remote camera locally, keep this tunnel open and use the original local viewer:

```bash
ssh -N -L 8555:localhost:8554 nvidia-accelerated-desktop---robotics-a223e8
./view.sh rtsp://localhost:8555/stream
```

The first launch downloads the referenced Carter asset. `demo/track.usda` is a fixed, untextured 20 × 16 m circuit with a 2.4 m lane and continuous red/white barriers, 0.8 m high and 0.22 m thick. The floor and both continuous wall meshes have static collision geometry. Wall sections share vertices, with red/white materials assigned per face, so there are no overlapping box faces at the joins. Curves use 24 segments per quarter turn and smooth side normals. To regenerate the static asset, run `python3 scripts/generate_track.py`; the simulator simply loads the USD. Carter starts on the straight facing the checkerboard; holding forward eventually drives it into a barrier. The main loop no longer reads the robot pose or moves the ground.
