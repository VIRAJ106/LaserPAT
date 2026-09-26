"""
servo_loop.py — High-level servo / actuator interface stub.

In a real PAT system this would interface with the gimbal servo drive over
serial/CAN/EtherCAT. In simulation, it wraps the software Gimbal model.

Architecture: The servo loop runs at a higher rate than the detection/Kalman
pipeline and applies the last commanded velocity or position between frame
updates (feed-forward hold).
"""
import time
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class ServoCommand:
    mode: str               # "VELOCITY" | "POSITION" | "HOLD"
    value_x: float = 0.0
    value_y: float = 0.0


class ServoLoop:
    """
    Software stub for a gimbal servo controller.

    In simulation mode the real hardware calls are replaced by direct
    mutation of the Gimbal object.  This class demonstrates the interface
    contract so it can be swapped for a real hardware driver at integration.

    Args:
        gimbal: The `Gimbal` instance from `src.camera.gimbal`.
        rate_hz: Update rate of the servo loop (default: 1 kHz).
    """

    def __init__(self, gimbal, rate_hz: float = 1000.0):
        self._gimbal = gimbal
        self._rate_hz = rate_hz
        self._dt = 1.0 / rate_hz
        self._last_cmd: Optional[ServoCommand] = None
        self._running = False

    # ------------------------------------------------------------------ #
    #  Command Interface (called from control thread at ~30 Hz)           #
    # ------------------------------------------------------------------ #
    def command_velocity(self, vx: float, vy: float) -> None:
        """Send a velocity command (px / frame) to the servo drive."""
        self._last_cmd = ServoCommand(mode="VELOCITY", value_x=vx, value_y=vy)

    def command_position(self, px: float, py: float) -> None:
        """Send a position command (world-space px) to the servo drive."""
        self._last_cmd = ServoCommand(mode="POSITION", value_x=px, value_y=py)

    def hold(self) -> None:
        """Hold current position — stops any ongoing slew."""
        self._last_cmd = ServoCommand(mode="HOLD")

    # ------------------------------------------------------------------ #
    #  Servo Execution (one step, called by simulation loop)              #
    # ------------------------------------------------------------------ #
    def step(self, dt: float) -> None:
        """
        Apply the last-received command.  In real hardware this runs at
        1 kHz in an interrupt; in simulation we call it once per frame.
        """
        if self._last_cmd is None:
            return

        cmd = self._last_cmd
        if cmd.mode == "VELOCITY":
            self._gimbal.command_velocity(cmd.value_x, cmd.value_y)
        elif cmd.mode == "POSITION":
            self._gimbal.command_position(cmd.value_x, cmd.value_y)
        # HOLD: do nothing, gimbal maintains last position internally

    # ------------------------------------------------------------------ #
    #  Telemetry                                                           #
    # ------------------------------------------------------------------ #
    def get_position(self) -> Tuple[float, float]:
        """Return current gimbal position (world-space px)."""
        return self._gimbal.get_position()

    def get_last_command(self) -> Optional[ServoCommand]:
        return self._last_cmd
