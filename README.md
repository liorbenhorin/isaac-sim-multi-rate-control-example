# Multi-rate Carter

A minimal standalone Isaac Sim 6.2 example: Nova Carter drives forward on an infinite collision plane with **300 Hz physics/IMU** and a **30 Hz camera streaming over RTSP**. `demo/scene.usda` contains the environment and a robot variant with its stock sensors disabled, plus one camera and one IMU.

## Run

From this directory, on either the local machine or Brev:

```bash
./run.sh
```

The launcher uses the adjacent `../IsaacSim` source build locally, or `~/robotics/isaacsim-6.2/.venv` on Brev. The source-build helper supplies this local Ubuntu installation's compatibility libraries. For another pip installation, run its Python directly:

```bash
/path/to/isaacsim/.venv/bin/python demo/carter_demo.py
```

Isaac's standard `--no-window` option runs without a GUI. The first launch downloads the referenced Nova Carter asset. Python constants set the physics/render rates, speed and resolution; camera pose and sensor tick rate live in `demo/scene.usda`. This example uses ten physics ticks per render.

Once the simulation is producing frames, in a second terminal:

```bash
./view.sh
```

Pixi installs the pinned GStreamer environment automatically, including H.264 parsing and decoding. The viewer prints FPS, RTP jitter, packet loss/late counts and display drops every **five wall-clock seconds**. Jitter is GStreamer's RTP arrival-jitter estimate, not end-to-end latency; drop/loss counts are cumulative. The simulator also prints one IMU reading every five wall-clock seconds, while reading the IMU on every physics tick.

The Brev copy is at `~/robotics/multi-rate-control`. To view its stream locally, open a tunnel and then run `./view.sh rtsp://localhost:8555/stream`:

```bash
ssh -N -L 8555:localhost:8554 nvidia-accelerated-desktop---robotics-a223e8
```

## Read the example

[`demo/scene.usda`](demo/scene.usda) holds the robot, infinite ground, lighting and sensor placements. [`demo/carter_demo.py`](demo/carter_demo.py) loads that scene, creates/configures physics, connects the sensors and RTSP writer, then owns the stepping loop. There are no demo-specific command-line options, async tasks, wrapper classes or CSV/JSON reporting.

```python
SimulationManager.step(steps=10)  # IMU callback runs after every physics step.
RenderingManager.render()       # One camera render and GUI update.
```

`/app/player/playSimulations=False` disables automatic physics during rendering. Each batch advances simulation time by 1/30 second. The sleep at the end of the loop targets 30 batches per wall-clock second; if computation takes longer, simulation runs slower than real time. Camera `tick_rate` controls its simulation-time cadence; it does not perform rendering by itself.

The textured ground mesh follows Carter so its edge stays out of view; its collision plane is infinite. The GUI viewpoint is set once and remains freely navigable. Close the simulator or press Ctrl+C to exit.

The bundled `demo/wireframe-blue.png` is the ground texture shipped with Isaac Sim’s `isaacsim.core.experimental.objects` extension.
