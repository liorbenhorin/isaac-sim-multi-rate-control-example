# Multi-rate control

Nova Carter driving forward on an infinite collision plane, with **300 Hz
physics and IMU** and one **30 Hz RTSP camera**. Tested with Isaac Sim
6.2.0-rc.14, both a local source build and the pip distribution.

## Run

From this directory, in separate terminals:

```bash
./run.sh
```

```bash
./view.sh
```

The simulator opens its GUI with a freely movable perspective. To follow the
robot instead, use `./run.sh --/carterDemo/follow=true`. The forward camera
streams H.264 at 1280x720 to `rtsp://localhost:8554/stream` independently of the
GUI view. `--no-window` makes the simulator headless while preserving rendering.

The robot settles for one simulation second, accelerates over two seconds,
and drives at a target 0.8 m/s through its wheel drives and ground contact.
The ground collider is infinite; a finite visual ground and 2 m grid recycle
around the robot, keeping the scene size constant.

## Brev instance

Instance: `nvidia-accelerated-desktop---robotics-a223e8`

Project: `/home/ubuntu/robotics/multi-rate-control`

In a terminal inside the **Brev desktop**, run:

```bash
cd ~/robotics/multi-rate-control
./run.sh
```

Open another desktop terminal for `./view.sh`. Both graphical windows appear
in the Brev desktop. For a headless run over SSH:

```bash
ssh nvidia-accelerated-desktop---robotics-a223e8
cd ~/robotics/multi-rate-control
./run.sh --no-window
```

To view the remote stream on your local workstation, keep this tunnel open
in a local terminal:

```bash
ssh -N -T -o ForwardAgent=no -L 127.0.0.1:8555:127.0.0.1:8554 nvidia-accelerated-desktop---robotics-a223e8
```

Then run from the **local** project directory:

```bash
./view.sh rtsp://localhost:8555/stream
```

The viewer forces RTSP-over-TCP, so the single forwarded port carries the
stream. No public RTSP firewall rule is needed. Stop/Play releases and
recreates the server; reconnect the viewer after Stop/Play.

The first tested pip launch took about 90 seconds to load the application,
followed by scene and shader initialization. Wait for the `[Carter]` rate
messages and nonzero camera FPS before connecting the viewer.

## Environments

`run.sh` detects the existing simulator in this order:

1. Explicit `ISAACSIM_LAUNCHER=/path/to/launcher` (an executable path).
2. Explicit `ISAACSIM_VENV=/path/to/venv` containing `bin/isaacsim`.
3. The adjacent source checkout's `../IsaacSim/run-local.sh`, preserving its
   Ubuntu/CUDA compatibility setup.
4. `~/robotics/isaacsim-6.2/.venv/bin/isaacsim`, the Brev pip installation.

The simulator uses its existing environment. The separate Pixi environment
here supplies the viewer. Do not launch the simulator from a shell that has
sourced system ROS: Brev's Humble uses Python 3.10, while Isaac uses 3.12.
This demo disables automatic ROS bridge startup; it consumes IMU data in
Python and optionally records CSV, without publishing ROS topics.

To install or verify the viewer:

```bash
./setup-viewer.sh
```

`pixi.toml` and `pixi.lock` pin GStreamer and its plugins from conda-forge.
`gst-plugins-bad` provides `h264parse`; `gst-libav` provides `avdec_h264`.
Everything installs under `.pixi/`; no system GStreamer packages are needed.
The helper finds Pixi on PATH, in `~/.pixi/bin`, or in the adjacent local
IsaacSim checkout's existing tool cache. `PIXI_BIN` overrides this lookup.

## Timing and data

```python
SimulationManager.setup_simulation(dt=1 / 300, device="cpu")
RenderingManager.set_dt(1 / 30)
```

Kit advances 1/30 simulation second per render/application update. PhysX
performs ten actual 1/300-second solver steps in that interval. The RTX
camera has `tick_rate=30`. The IMU updates on every physics step; its callback
reads at post-step order 100, after the built-in IMU update at order 1.

At real-time speed, this yields 300 IMU samples and 30 camera frames per
wall-clock second. Under load, simulated time slows down while the simulation
time spacing remains fixed. Terminal status reports observed wall rates,
simulation time, position and accelerometer values once per second.

Record all IMU samples and a run summary:

```bash
./run.sh --/carterDemo/imuCsv=outputs/imu.csv --/carterDemo/summary=outputs/summary.json
```

For a bounded check:

```bash
./run.sh --no-window --/carterDemo/duration=30 --/carterDemo/imuCsv=outputs/imu.csv --/carterDemo/summary=outputs/summary.json
python3 scripts/check-run.py outputs/summary.json outputs/imu.csv
```

CSV contains physics step, sensor simulation time, accelerometer XYZ (m/s²),
gyroscope XYZ (rad/s), and quaternion WXYZ. Sensor axes are chassis X forward,
Y left, Z up. Acceleration is specific force: approximately `(0, 0, 9.81)` at
rest. Filter widths are 1, with no added synthetic noise. The first samples
include settling transients. Files are overwritten at the selected paths.
Stop/Play resets sensor timestamps; the CSV step counter continues.

## Options

All options use `--/carterDemo/NAME=VALUE`:

| Setting | Default | Meaning |
|---|---|---|
| `physicsHz` | 300 | Integer physics rate; integer multiple of camera rate |
| `cameraHz` | 30 | Camera and application/render rate |
| `speed` | 0.8 | Forward wheel-command target, m/s |
| `width`, `height` | 1280, 720 | Positive even image dimensions |
| `port`, `mountPath` | 8554, `/stream` | RTSP endpoint |
| `follow` | false | Follow Carter in the GUI |
| `duration` | 0 | Wall-clock seconds after setup; 0 runs until closed |
| `imuCsv`, `summary` | empty | Optional output paths |

## Project files

- `demo/carter_demo.py`: scene, wheel control, IMU callbacks and stream setup.
- `demo/nova_carter_light.usda`: small overlay selecting the shipped robot's
  `Sensors=None`, `Configuration=No_Internals`, `Physics=physx`, `ROS=Disabled`
  variants. The script adds one camera and one IMU and rejects leftover stock
  sensors. NVIDIA assets download on the first uncached load.
- `run.sh`: simulator launcher for source and pip installations.
- `view.sh`, `setup-viewer.sh`, `scripts/pixi.sh`: isolated GStreamer viewer.
- `scripts/check-run.py`: validates sample timestamps and the step/frame ratio
  from a continuous bounded run.

The encoder and RTSP server are Isaac Sim's shipped `RTSPStreamWriter`.
The demo subclass only counts nonempty encoded frames for diagnostics.
Generated environments, captures and logs are excluded from Git.

## Validation

The initial standalone-project checks passed on both installations:

| Runtime | Physics steps / IMU samples | Physics steps per update | Encoded frames |
|---|---|---|---|
| Local source build | 2,960 / 2,960 | 10 | 293 |
| Brev pip installation | 8,460 / 8,460 | 10 | 843 |

IMU timestamp spacing was approximately 3.333 ms. Encoder startup accounts
for the first three missing encoded frames. The remote Pixi client decoded
a 1280x720 frame successfully. Observed remote wall rates varied around
270–300 physics/IMU Hz and 27–30 camera FPS after initialization; the
simulation-time rates remained 300/30 Hz.
