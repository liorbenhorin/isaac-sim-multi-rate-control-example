"""GUI throttle/steering commands and IMU readout in a separate ROS 2 process."""

import threading
import time
import tkinter as tk
from tkinter import ttk

import rclpy
from geometry_msgs.msg import Twist
from rclpy.duration import Duration
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import Imu


class CarterControl(Node):
    def __init__(self):
        super().__init__("carter_control")
        self.command = Twist()
        self.imu = None
        self.samples = 0
        self.received_at = 0.0
        self.publisher = self.create_publisher(Twist, "/cmd_vel", 10)
        self.create_subscription(Imu, "/chassis/imu", self.read_imu,
                                 QoSProfile(depth=100, reliability=ReliabilityPolicy.BEST_EFFORT))
        self.create_timer(0.05, lambda: self.publisher.publish(self.command))

    def read_imu(self, message):
        self.imu = message
        self.samples += 1
        self.received_at = time.monotonic()


def make_window(node):
    root = tk.Tk()
    root.title("Nova Carter — Drive")
    root.resizable(False, False)
    root.option_add("*Font", "{DejaVu Sans} 11")
    ttk.Label(root, text="Nova Carter", font=("DejaVu Sans", 18, "bold")).pack(pady=(16, 4))
    ttk.Label(root, text="Sliders hold their settings. Space or Esc stops.").pack(padx=20, pady=(0, 8))

    def change(_=None):
        command = Twist()
        command.linear.x = throttle.get()
        command.angular.z = steering.get()
        node.command = command

    throttle = tk.Scale(root, name="throttle", from_=-1.0, to=1.0, resolution=0.05,
                        orient="horizontal", length=480, command=change,
                        label="Throttle (m/s): reverse ← → forward")
    throttle.pack(padx=20, pady=8)
    steering = tk.Scale(root, name="steering", from_=1.2, to=-1.2, resolution=0.05,
                        orient="horizontal", length=480, command=change,
                        label="Steering (rad/s): left ← → right")
    steering.pack(padx=20, pady=8)

    def stop(event=None):
        throttle.set(0)
        steering.set(0)
        node.command = Twist()
        node.publisher.publish(node.command)
        return "break"

    tk.Button(root, name="stop", text="STOP  ·  Space", command=stop,
              bg="#bc3037", fg="white", activebackground="#99252b", activeforeground="white",
              font=("DejaVu Sans", 15, "bold")).pack(fill="x", padx=24, pady=(8, 6))
    ttk.Button(root, name="straighten", text="Straighten steering", command=lambda: steering.set(0)).pack(
        fill="x", padx=24, pady=(0, 12))
    status = tk.StringVar(value="Waiting for IMU…\n\n")
    ttk.Label(root, name="status", textvariable=status, justify="left", width=55).pack(padx=24, pady=(0, 16))
    root.bind("<space>", stop)
    root.bind("<Escape>", stop)
    root.protocol("WM_DELETE_WINDOW", root.quit)
    last_time, last_count, rate = time.monotonic(), 0, 0.0

    def refresh():
        nonlocal last_time, last_count, rate
        now = time.monotonic()
        if now - last_time >= 1:
            rate = (node.samples - last_count) / (now - last_time)
            last_time, last_count = now, node.samples
        message = node.imu
        if message is None or now - node.received_at > 1:
            status.set("No IMU data — simulator stopped or disconnected\n\n")
        else:
            a, g, stamp = message.linear_acceleration, message.angular_velocity, message.header.stamp
            status.set(f"IMU: {rate:.0f} samples/s    Time: {stamp.sec + stamp.nanosec / 1e9:.2f}s\n"
                       f"Acceleration: {a.x:.2f}, {a.y:.2f}, {a.z:.2f} m/s²\n"
                       f"Measured turn rate: {g.z:.2f} rad/s")
        root.after(200, refresh)

    refresh()
    return root


def main():
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = CarterControl()
    root = make_window(node)
    # ROS drains the 300 Hz IMU stream independently of Tk's main UI thread.
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    worker = threading.Thread(target=executor.spin, daemon=True)
    worker.start()
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        node.command = Twist()
        executor.shutdown()
        worker.join()
        node.publisher.publish(node.command)
        node.publisher.wait_for_all_acked(Duration(seconds=0.2))
        node.destroy_node()
        rclpy.shutdown()
        root.destroy()


if __name__ == "__main__":
    main()
