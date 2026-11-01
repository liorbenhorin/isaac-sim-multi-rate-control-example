"""Keyboard throttle/turn commands and IMU readout, running in a separate ROS 2 process."""

import os
import select
import sys
import termios
import time
import tty

import rclpy
from geometry_msgs.msg import Twist
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
        self.last_report = time.monotonic()
        self.publisher = self.create_publisher(Twist, "/cmd_vel", 10)
        self.create_subscription(Imu, "/chassis/imu", self.read_imu,
                                 QoSProfile(depth=100, reliability=ReliabilityPolicy.BEST_EFFORT))
        self.create_timer(0.05, lambda: self.publisher.publish(self.command))
        self.create_timer(5.0, self.report)

    def read_imu(self, message):
        self.imu = message
        self.samples += 1

    def key(self, key):
        if key in "ws":
            self.command.linear.x = max(-1.0, min(1.0, self.command.linear.x + (0.1 if key == "w" else -0.1)))
        elif key in "ad":
            self.command.angular.z = max(-1.2, min(1.2, self.command.angular.z + (0.1 if key == "a" else -0.1)))
        elif key == " ":
            self.command = Twist()

    def report(self):
        now = time.monotonic()
        status = f"speed={self.command.linear.x:.1f}m/s turn={self.command.angular.z:.1f}rad/s"
        if self.imu is not None:
            a, g = self.imu.linear_acceleration, self.imu.angular_velocity
            stamp = self.imu.header.stamp
            status += (f" | IMU={self.samples / (now - self.last_report):.1f}Hz "
                       f"t={stamp.sec + stamp.nanosec / 1e9:.3f}s "
                       f"accel=({a.x:.2f}, {a.y:.2f}, {a.z:.2f})m/s² gyro.z={g.z:.2f}rad/s")
        else:
            status += " | waiting for IMU"
        print(status, flush=True)
        self.samples, self.last_report = 0, now


def main():
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = CarterControl()
    terminal = termios.tcgetattr(sys.stdin)
    print("W/S: speed ±0.1m/s | A/D: turn ±0.1rad/s | Space: stop | Q: quit", flush=True)
    try:
        tty.setcbreak(sys.stdin.fileno())
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.05)
            if select.select([sys.stdin], [], [], 0)[0]:
                key = os.read(sys.stdin.fileno(), 1).decode().lower()
                if key == "q":
                    break
                node.key(key)
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, terminal)
        node.command = Twist()
        node.publisher.publish(node.command)
        rclpy.spin_once(node, timeout_sec=0.1)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
