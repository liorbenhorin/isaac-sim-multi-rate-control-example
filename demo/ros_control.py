"""Gamepad → ROS 2 velocity commands, with a quiet IMU readout."""

import math
import os
import signal
import struct
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import Imu


def stick(value):
    """Normalize a Linux joystick axis with a 10% dead zone."""
    value = max(-1.0, min(1.0, value / 32767))
    return math.copysign(max(0.0, (abs(value) - 0.1) / 0.9), value)


class CarterControl(Node):
    def __init__(self):
        super().__init__("carter_control")
        self.joystick = os.open("/dev/input/js0", os.O_RDONLY | os.O_NONBLOCK)
        self.axes = [0, 0]  # Left stick X/Y: native DualSense and Selkies Xbox 360 mapping.
        self.enabled = False
        self.imu = None
        self.samples = 0
        self.reported_at = time.monotonic()
        self.publisher = self.create_publisher(Twist, "/cmd_vel", 10)
        self.create_subscription(Imu, "/chassis/imu", self.read_imu,
                                 QoSProfile(depth=100, reliability=ReliabilityPolicy.BEST_EFFORT))
        self.create_timer(0.05, self.drive)
        self.create_timer(5.0, self.report)

    def drive(self):
        while True:
            try:
                event = os.read(self.joystick, 8)
            except BlockingIOError:
                break
            if not event:
                raise OSError("Joystick disconnected")
            # Linux js_event: timestamp, signed value, type, axis/button index.
            _, value, kind, number = struct.unpack("IhBB", event)
            kind &= ~0x80  # Initial-state events carry the same axis/button data.
            if kind == 2 and number < 2:
                self.axes[number] = value
            elif kind == 1 and number == 4:  # L1 / left bumper: hold to drive.
                self.enabled = bool(value)
        command = Twist()
        if self.enabled:
            throttle, steering = -stick(self.axes[1]), -stick(self.axes[0])
            # Slow down in corners; softer steering near center makes small corrections easier.
            command.linear.x = 2.0 * throttle * (1.0 - 0.75 * abs(steering))
            command.angular.z = 1.2 * steering * abs(steering)
        self.publisher.publish(command)

    def read_imu(self, message):
        self.imu = message
        self.samples += 1

    def report(self):
        now = time.monotonic()
        rate = self.samples / (now - self.reported_at)
        if self.samples:
            a, g = self.imu.linear_acceleration, self.imu.angular_velocity
            print(f"IMU {rate:.0f} Hz | acceleration {a.x:.2f}, {a.y:.2f}, {a.z:.2f} m/s²"
                  f" | yaw rate {g.z:.2f} rad/s", flush=True)
        else:
            print("Waiting for IMU…", flush=True)
        self.samples, self.reported_at = 0, now


def main():
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    node = CarterControl()
    print("Hold L1 + left stick: up/down = forward/reverse, left/right = turn."
          " Release L1 to stop. Ctrl+C exits.", flush=True)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.publisher.publish(Twist())
        node.publisher.wait_for_all_acked(Duration(seconds=0.2))
        os.close(node.joystick)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
