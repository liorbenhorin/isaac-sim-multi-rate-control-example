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

### Viewer statistics

`./view.sh` prints live receiver statistics once per second while displaying
the video. It uses Python GStreamer bindings from the project's Pixi environment.

```bash
# Decode and measure over SSH without a display.
./view.sh --headless --duration=15

# Measure a forwarded remote stream, reporting every two seconds.
./view.sh rtsp://localhost:8555/stream --interval=2

# Video only, or change the jitter-buffer target.
./view.sh --no-stats
./view.sh --latency-ms=50
```

| Output | Meaning |
|---|---|
| `decoded`, `sink` | Decoded and video-sink frames per receiver wall second; headless sink consumes frames without displaying them |
| `H264` | Parsed H.264 payload bitrate, excluding network overhead |
| `gap mean/std/max` | Time between decoded frames in milliseconds; standard deviation describes frame-arrival variability |
| `idle` | Wall time since the last decoded frame; exposes a stalled stream |
| `RTP jitter` | GStreamer's smoothed RTP packet jitter estimate, converted to milliseconds |
| `lost`, `late`, `dup` | Cumulative RTP jitter-buffer packet counters for this connection |
| `sink drops` | Cumulative video-sink frame-drop counter |

Frame gaps include effects of buffering, decoding, scheduling and downstream
backpressure; they are not a pure network measurement. RTP jitter is a separate
packet-level statistic. TCP can recover network packet loss while causing
delivery stalls, so zero RTP loss does not establish a perfect network path.
Neither metric measures camera-to-display latency. `--latency-ms` configures a
buffering target, not a measured end-to-end delay. During startup the sink can
lag decoding while its queue fills.

Field definitions follow GStreamer's [RTP jitter-buffer statistics](https://gstreamer.freedesktop.org/documentation/rtpmanager/rtpjitterbuffer.html#rtpjitterbuffer:stats)
and [FPS display sink counters](https://gstreamer.freedesktop.org/documentation/debugutilsbad/fpsdisplaysink.html).

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

1. Explicit `ISAACSIM_PYTHON=/path/to/python-launcher` (configured Python).
2. Explicit `ISAACSIM_VENV=/path/to/venv` containing `bin/python`.
3. `ISAACSIM_SOURCE_ROOT` or the adjacent `../IsaacSim` source checkout.
   `scripts/source-python.sh` uses its `python.sh` with the existing
   libxml2/CUDA compatibility environment.
4. `~/robotics/isaacsim-6.2/.venv/bin/python`, the Brev pip installation.

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

This is a **standalone Python application**. `demo/main.py` creates
`SimulationApp` before importing any Kit-dependent code and closes it on exit.
After releasing the stream, callbacks and CSV file, it uses Isaac's default
fast shutdown with an explicit exit code, preserving configuration/runtime errors.
`CarterDemo.run()` owns the main thread. There are no async demo functions,
scheduled asyncio tasks, or `--exec` scripts driving the simulation.

The core loop is synchronous:

```python
SimulationManager.setup_simulation(dt=1 / 300, device="cpu")
RenderingManager.set_dt(1 / 30)

while simulation_app.is_running():
    if timeline.is_playing():
        SimulationManager.step(steps=10)  # Physics only; IMU callback after each step.
    RenderingManager.render()            # Render + GUI input; no physics step.
    # Pace the loop against a monotonic wall-clock deadline at 30 Hz.
```

The actual loop also handles Stop/Play, checks for errors, and waits for its
wall-clock deadline. Automatic physics during app updates is disabled with
`/app/player/playSimulations=false`. Each render is checked to ensure it did
not advance physics. Kit's internal rate limiter is disabled; the Python main
loop owns pacing and avoids catch-up bursts after stalls. Physics initialization
performs engine warm-up before the measured explicit steps.

The RTX camera has `tick_rate=30`. The IMU updates on every physics step; its
synchronous callback reads at post-step order 100, after the built-in IMU
update at order 1. Each camera interval therefore contains ten real solver
steps and ten distinct IMU samples. Extra per-substep Fabric updates are not
requested; the normal render path handles the visual update.

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

- `demo/main.py`: standalone `SimulationApp` lifecycle.
- `demo/carter_demo.py`: synchronous main loop, scene, wheel control, IMU callbacks and stream setup.
- `demo/nova_carter_light.usda`: small overlay selecting the shipped robot's
  `Sensors=None`, `Configuration=No_Internals`, `Physics=physx`, `ROS=Disabled`
  variants. The script adds one camera and one IMU and rejects leftover stock
  sensors. NVIDIA assets download on the first uncached load.
- `run.sh`, `scripts/source-python.sh`: standalone Python launchers for pip and source installations.
- `view.sh`, `scripts/rtsp_viewer.py`, `setup-viewer.sh`, `scripts/pixi.sh`: isolated GStreamer viewer and statistics.
- `scripts/check-run.py`: validates sample timestamps and the step/frame ratio
  from a continuous bounded run.

The encoder and RTSP server are Isaac Sim's shipped `RTSPStreamWriter`.
The demo subclass only counts nonempty encoded frames for diagnostics.
Generated environments, captures and logs are excluded from Git.

## Validation

The standalone main loop has been exercised locally and on the Brev pip
installation with one distinct IMU sample per explicit physics step, 3.333 ms
sample spacing, and ten steps per render. The loop verifies that rendering
adds no physics steps. GUI Pause/Resume and Stop/Play were also checked,
including IMU timestamp reset and resumed RTSP streaming.

The local viewer measured approximately 30 decoded/displayed FPS and 33.33 ms
mean frame spacing. The Brev viewer observed roughly 26–28 FPS in the measured
window, reflecting the remote simulator's wall-clock throughput. Both reported
RTP jitter separately from decoded-frame variability and zero reported RTP
loss/sink drops in those checks. Simulation-time rates remain 300/30 Hz.
