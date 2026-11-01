# Multi-rate Carter with ROS 2 — Brev

This branch adds ROS 2 control to the demo. Keep the local repository and Brev copy in sync; run simulation and ROS tests on Brev at `~/robotics/multi-rate-control`. The launchers below target its existing Isaac Sim pip environment and system ROS 2 Humble.

## Run

Open three terminals on Brev, each in `~/robotics/multi-rate-control`:

```bash
./run.sh       # Isaac Sim: 300 Hz physics/IMU, 30 Hz camera
./control.sh   # ROS 2 GUI controller and IMU readout
./view.sh      # RTSP viewer
```

Run each command in its own terminal. `./run.sh --no-window` runs Isaac without a GUI. The controller uses the installed system ROS 2 Humble/Python 3.10; Isaac uses its bundled Humble bridge with Python 3.12. Neither script requires sourcing ROS in the parent terminal.

Carter starts stationary. `./control.sh` opens a small controller window on the **Brev desktop**, including when launched over SSH (the default display is `:99`). Isaac itself can stay headless.

- **Throttle slider:** forward/reverse speed, from −1 to +1 m/s.
- **Steering slider:** drag left to turn left, right to turn right (up to 1.2 rad/s).
- **Straighten steering:** zero the turning rate while keeping the throttle setting.
- **STOP**, **Space**, or **Esc:** immediately zero both commands.
- **Close the window:** send a stop command and exit.

Sliders hold their settings until changed. Commands publish at 20 Hz. The window shows the latest IMU acceleration, measured turn rate, simulation timestamp and received sample rate, without periodic console output. The received rate uses wall time, so it falls below 300 Hz when simulation runs slower than real time.

## How it works

`demo/scene.usda` selects Carter's shipped `ROS="Enabled"` and `Sensors="None"` variants. The stock sensor branch and odometry/TF graph are disabled; the scene contains one camera and one IMU.

The shipped differential-drive graph subscribes to **`/cmd_vel` (`geometry_msgs/Twist`)** and converts forward speed (`linear.x`) and yaw rate (`angular.z`) to wheel commands. It processes commands on each render/app update; physics integrates those commands at 300 Hz.

The shipped IMU graph is retargeted to our sensor and publishes **`/chassis/imu` (`sensor_msgs/Imu`)**, with frame ID `carter_imu` and sensor simulation-time timestamps. Python triggers that graph after each physics tick, after the IMU backend updates. IMU reading and ROS message construction happen in the shipped graph nodes.

`demo/carter_demo.py` creates/configures physics, runs ten physics ticks per render, and streams the camera using Isaac's RTSP writer. `demo/ros_control.py` is the separate ROS controller/subscriber. Physics configuration stays in Python; static scene and bridge wiring stay in USD. The 300/30 Hz rates are in simulation time; wall-clock sleep targets real time, but computation can make the simulator run slower.

The GUI viewpoint remains freely navigable. The RTSP viewer reports FPS/jitter every five seconds. To view the remote camera locally, keep this tunnel open and use the original local viewer:

```bash
ssh -N -L 8555:localhost:8554 nvidia-accelerated-desktop---robotics-a223e8
./view.sh rtsp://localhost:8555/stream
```

The first launch downloads the referenced Carter asset. `demo/track.usda` is a fixed, untextured 20 × 16 m circuit with a 2.4 m lane and continuous red/white barriers, 0.8 m high and 0.22 m thick. The floor and barrier blocks have static collision geometry. Carter starts on the straight facing the checkerboard; holding forward eventually drives it into a barrier. The main loop no longer reads the robot pose or moves the ground.
