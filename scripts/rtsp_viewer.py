"""Display an H.264 RTSP stream and report receiver-side timing and RTP statistics."""

from __future__ import annotations

import argparse
import math
import signal
import sys
import threading
import time

import gi

gi.require_version("Gst", "1.0")
from gi.repository import GLib, GLibUnix, Gst


class Viewer:
    """Collect counters on streaming threads and print snapshots on the GLib loop."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.lock = threading.Lock()
        self.frames = 0
        self.total_frames = 0
        self.payload_bytes = 0
        self.gap_count = 0
        self.gap_sum = 0.0
        self.gap_squares = 0.0
        self.gap_max = 0.0
        self.last_frame = None
        self.last_report = time.monotonic()
        self.last_rendered = 0
        self.jitterbuffers = []
        self.exit_code = 0
        self.loop = GLib.MainLoop()
        self.pipeline = Gst.parse_launch(
            "rtspsrc name=source protocols=tcp ! application/x-rtp,media=video,encoding-name=H264 "
            "! rtph264depay ! h264parse name=parser ! avdec_h264 name=decoder "
            "! queue max-size-buffers=60 max-size-bytes=0 max-size-time=0 "
            "! videoconvert ! fpsdisplaysink name=display text-overlay=false silent=true sync=true"
        )
        source = self.pipeline.get_by_name("source")
        source.set_property("location", args.url)
        source.set_property("latency", args.latency_ms)
        source.connect("new-manager", self.on_manager)
        self.display = self.pipeline.get_by_name("display")
        sink = Gst.ElementFactory.make("fakesink" if args.headless else "autovideosink")
        if sink is None:
            raise RuntimeError("Video sink unavailable; run ./setup-viewer.sh")
        self.display.set_property("video-sink", sink)
        self.pipeline.get_by_name("decoder").get_static_pad("src").add_probe(Gst.PadProbeType.BUFFER, self.on_frame)
        self.pipeline.get_by_name("parser").get_static_pad("src").add_probe(Gst.PadProbeType.BUFFER, self.on_payload)
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect("message", self.on_message)

    def on_manager(self, source: Gst.Element, manager: Gst.Element) -> None:
        manager.connect("new-jitterbuffer", self.on_jitterbuffer)

    def on_jitterbuffer(self, manager: Gst.Element, buffer: Gst.Element, session: int, ssrc: int) -> None:
        with self.lock:
            self.jitterbuffers.append(buffer)

    def on_payload(self, pad: Gst.Pad, info: Gst.PadProbeInfo) -> Gst.PadProbeReturn:
        buffer = info.get_buffer()
        if buffer is not None:
            with self.lock:
                self.payload_bytes += buffer.get_size()
        return Gst.PadProbeReturn.OK

    def on_frame(self, pad: Gst.Pad, info: Gst.PadProbeInfo) -> Gst.PadProbeReturn:
        now = time.monotonic()
        with self.lock:
            self.frames += 1
            self.total_frames += 1
            if self.last_frame is not None:
                gap = (now - self.last_frame) * 1000
                self.gap_count += 1
                self.gap_sum += gap
                self.gap_squares += gap * gap
                self.gap_max = max(self.gap_max, gap)
            self.last_frame = now
        return Gst.PadProbeReturn.OK

    def report(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_report
        self.last_report = now
        with self.lock:
            frames, payload = self.frames, self.payload_bytes
            count, gap_sum, squares, gap_max = self.gap_count, self.gap_sum, self.gap_squares, self.gap_max
            last_frame = self.last_frame
            buffers = list(self.jitterbuffers)
            self.frames = self.payload_bytes = self.gap_count = 0
            self.gap_sum = self.gap_squares = self.gap_max = 0.0
        rendered = self.display.get_property("frames-rendered")
        dropped = self.display.get_property("frames-dropped")
        sink_fps = (rendered - self.last_rendered) / elapsed
        self.last_rendered = rendered
        if count:
            mean = gap_sum / count
            deviation = math.sqrt(max(0, squares / count - mean * mean))
            gap_text = f"{mean:.2f}/{deviation:.2f}/{gap_max:.2f}ms"
        else:
            gap_text = "n/a"
        idle = "waiting" if last_frame is None else f"{(now-last_frame)*1000:.0f}ms"
        rtp_text = "RTP waiting"
        if buffers:
            stats = [buffer.get_property("stats") for buffer in buffers]
            stats = [item for item in stats if item is not None]
            if stats:
                # GStreamer's avg-jitter is its smoothed RTP jitter estimate in nanoseconds.
                jitter = max(int(item.get_value("avg-jitter") or 0) for item in stats) / 1e6
                totals = {
                    name: sum(int(item.get_value(name) or 0) for item in stats)
                    for name in ("num-lost", "num-late", "num-duplicates")
                }
                rtp_text = (
                    f"RTP jitter={jitter:.2f}ms lost={totals['num-lost']} "
                    f"late={totals['num-late']} dup={totals['num-duplicates']}"
                )
        if not self.args.no_stats:
            print(
                f"[RTSP] decoded={frames/elapsed:.1f}fps sink={sink_fps:.1f}fps "
                f"H264={payload*8/elapsed/1e6:.2f}Mb/s | gap mean/std/max={gap_text} "
                f"idle={idle} | {rtp_text} | sink drops={dropped}",
                flush=True,
            )
        return GLib.SOURCE_CONTINUE

    def on_message(self, bus: Gst.Bus, message: Gst.Message) -> None:
        if message.type == Gst.MessageType.ERROR:
            error, debug = message.parse_error()
            print(f"[RTSP] Error: {error.message}", file=sys.stderr, flush=True)
            if self.args.debug and debug:
                print(debug, file=sys.stderr)
            self.exit_code = 1
            self.loop.quit()
        elif message.type == Gst.MessageType.EOS:
            print("[RTSP] Stream ended", flush=True)
            self.loop.quit()
        elif message.type == Gst.MessageType.LATENCY:
            self.pipeline.recalculate_latency()

    def stop(self) -> bool:
        self.loop.quit()
        return GLib.SOURCE_REMOVE

    def run(self) -> int:
        print(f"[RTSP] Connecting over TCP; jitter-buffer target={self.args.latency_ms}ms", flush=True)
        if not self.args.no_stats:
            print(
                "[RTSP] Rates/gaps use receiver wall time; loss/late/dup/drop counters are cumulative. "
                "Buffer target is not measured end-to-end latency.",
                flush=True,
            )
        GLib.timeout_add(round(self.args.interval * 1000), self.report)
        if self.args.duration:
            GLib.timeout_add(round(self.args.duration * 1000), self.stop)
        GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self.stop)
        GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self.stop)
        try:
            if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
                print("[RTSP] Could not start playback", file=sys.stderr)
                return 1
            self.loop.run()
            self.report()
            if not self.total_frames:
                print("[RTSP] No video frames decoded", file=sys.stderr)
                return 1
            return self.exit_code
        finally:
            self.pipeline.set_state(Gst.State.NULL)
            self.bus.remove_signal_watch()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?", default="rtsp://localhost:8554/stream")
    parser.add_argument("--headless", action="store_true", help="Decode and measure without opening a window")
    parser.add_argument("--no-stats", action="store_true", help="Hide periodic statistics")
    parser.add_argument("--interval", type=float, default=1, help="Reporting interval in seconds (default: 1)")
    parser.add_argument("--latency-ms", type=int, default=100, help="Jitter-buffer target in ms (default: 100)")
    parser.add_argument("--duration", type=float, default=0, help="Exit after this many wall seconds; 0 is unlimited")
    parser.add_argument("--debug", action="store_true", help="Print detailed GStreamer errors")
    args = parser.parse_args()
    if not math.isfinite(args.interval) or args.interval < 0.1:
        parser.error("--interval must be finite and at least 0.1 seconds")
    if not math.isfinite(args.duration) or args.duration < 0 or args.latency_ms < 0:
        parser.error("--duration and --latency-ms must be nonnegative and finite")
    if not args.url.startswith(("rtsp://", "rtsps://")):
        parser.error("URL must start with rtsp:// or rtsps://")
    Gst.init(None)
    try:
        return Viewer(args).run()
    except (GLib.Error, RuntimeError) as error:
        print(f"[RTSP] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
