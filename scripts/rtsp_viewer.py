"""Show the camera stream; print receiver FPS, RTP jitter and drops every five seconds."""

import sys
import time

import gi

gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst

Gst.init(None)
loop = GLib.MainLoop()
pipeline = Gst.parse_launch(
    "rtspsrc name=source protocols=tcp latency=100 ! application/x-rtp,media=video,encoding-name=H264 "
    "! rtph264depay ! h264parse ! avdec_h264 ! videoconvert "
    "! fpsdisplaysink name=display text-overlay=false silent=true sync=true"
)
source = pipeline.get_by_name("source")
source.set_property("location", sys.argv[1] if len(sys.argv) > 1 else "rtsp://localhost:8554/stream")
display = pipeline.get_by_name("display")
jitterbuffers = []
last_time, last_frames = time.monotonic(), 0
exit_code = 0


def on_manager(source, manager):
    manager.connect("new-jitterbuffer", lambda manager, buffer, session, ssrc: jitterbuffers.append(buffer))


def report():
    global last_time, last_frames
    now = time.monotonic()
    frames = display.get_property("frames-rendered")
    print(f"FPS={(frames - last_frames) / (now - last_time):.1f} | "
          f"display drops={display.get_property('frames-dropped')}", end="", flush=True)
    for buffer in jitterbuffers:
        stats = buffer.get_property("stats")
        print(f" | RTP jitter={stats.get_value('avg-jitter') / 1e6:.2f}ms "
              f"lost={stats.get_value('num-lost')} late={stats.get_value('num-late')}", end="")
    print(flush=True)
    last_time, last_frames = now, frames
    return GLib.SOURCE_CONTINUE


def on_message(bus, message):
    global exit_code
    if message.type == Gst.MessageType.ERROR:
        print(message.parse_error()[0].message, file=sys.stderr)
        exit_code = 1
        loop.quit()
    elif message.type == Gst.MessageType.EOS:
        loop.quit()
    elif message.type == Gst.MessageType.LATENCY:
        pipeline.recalculate_latency()


source.connect("new-manager", on_manager)
bus = pipeline.get_bus()
bus.add_signal_watch()
bus.connect("message", on_message)
GLib.timeout_add_seconds(5, report)
pipeline.set_state(Gst.State.PLAYING)
try:
    loop.run()
except KeyboardInterrupt:
    pass
pipeline.set_state(Gst.State.NULL)
sys.exit(exit_code)
