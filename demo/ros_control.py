"""Gamepad → ROS 2 velocity commands."""

import math
import os
import signal
import struct

import rclpy
from geometry_msgs.msg import Twist
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.signals import SignalHandlerOptions


def stick(value):
    """Normalize a Linux joystick axis with a 10% dead zone."""
    value = max(-1.0, min(1.0, value / 32767))
    return math.copysign(max(0.0, (abs(value) - 0.1) / 0.9), value)


class CarterControl(Node):
    def __init__(self):
        super().__init__("carter_control")
        self.joystick = os.open("/dev/input/js0", os.O_RDONLY | os.O_NONBLOCK)
        self.axes = [0, 0]  # Left stick X/Y: native DualSense and Selkies Xbox 360 mapping.
        self.publisher = self.create_publisher(Twist, "/cmd_vel", 10)
        self.create_timer(0.05, self.drive)

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
        command = Twist()
        throttle, steering = -stick(self.axes[1]), -stick(self.axes[0])
        command.linear.x = throttle  # Carter's shipped maximum: 1 m/s.
        # Throttle demand reduces steering authority: 1.2 rad/s stopped, 0.2 rad/s at full throttle.
        # At 1 m/s, full steering therefore commands a 5 m radius. Reverse uses the same limit.
        yaw_limit = 1.2 * (1.0 - abs(throttle)) + 0.2 * abs(throttle)
        command.angular.z = yaw_limit * steering * abs(steering)
        self.publisher.publish(command)


def main():
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    node = CarterControl()
    print("Left stick: up/down = forward/reverse, left/right = steering."
          " Center the stick to stop. Ctrl+C exits.", flush=True)
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
