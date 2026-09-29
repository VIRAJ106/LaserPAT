"""
interfaces.py — Shared architectural contracts for LaserPAT.

This module is the single source of truth for every cross-layer data
structure and Protocol used in the PAT pipeline.  Nothing in this file
imports from any other src.* module, keeping the import graph acyclic.

Canonical pipeline order
------------------------
    Scenario → World → Platform/Gimbal pose → DisturbanceState → SensorFrame
    → PerceptionResult → CandidateManager → TargetIdentity
    → PATSupervisor → PATCommand → GimbalActuator → next frame
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# 1.  World / geometry contracts
# ---------------------------------------------------------------------------

@dataclass
class RelativeGeometry:
    """
    Coarse 3D geometry between the transmitter and receiver terminals.

    In the current implementation the fields are populated from the 2-D world
    simulation (z=0 plane); the architecture is ready for a full 6-DoF upgrade.
    """
    range_m: float = 1000.0            # Slant range between terminals (metres)
    azimuth_rad: float = 0.0           # Azimuth angle from receiver to transmitter
    elevation_rad: float = 0.0         # Elevation angle (positive = above horizon)
    # Platform attitude (roll, pitch, yaw in radians) — zero for 2-D simulation
    platform_attitude: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    # Unit line-of-sight vector in world frame [x, y, z]
    los_vector: Tuple[float, float, float] = (0.0, 0.0, 1.0)


# ---------------------------------------------------------------------------
# 2.  Disturbance contracts
# ---------------------------------------------------------------------------

@dataclass
class DisturbanceState:
    """
    Unified disturbance state produced each frame by DisturbanceModel.

    Replaces the independent per-subsystem generators (jitter.py, noise.py,
    weather.py, and Platform.jitter_max_px) with one causal object that
    propagates platform motion → optical turbulence → sensor noise.
    """
    # Platform mechanical disturbances
    platform_tx_px: float = 0.0          # Translation jitter X (pixels)
    platform_ty_px: float = 0.0          # Translation jitter Y (pixels)
    platform_roll_rad: float = 0.0       # Rotation disturbance (radians)

    # Atmospheric / optical disturbances
    optical_blur_sigma_px: float = 0.0   # Gaussian blur from Cn² turbulence
    beam_wander_px: float = 0.0          # Far-field beam displacement estimate

    # Sensor noise parameters (applied to image)
    sensor_gaussian_sigma: float = 0.0
    sensor_poisson: bool = False
    sensor_sp_percent: float = 0.0

    # Atmospheric transmittance (Beer-Lambert) — scalar ∈ [0, 1]
    atmospheric_transmittance: float = 1.0

    # Weather label for logging
    weather_preset: str = "clear"


# ---------------------------------------------------------------------------
# 3.  Detection / perception contracts
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    """
    A single blob/detection from any perception backend.

    Fields are a strict superset of the raw (x, y, w, h) tuple so that
    CandidateManager can fuse features without back-casting.
    """
    # Bounding box in sensor-frame pixel coordinates (top-left origin)
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0

    # Centroid (sub-pixel, intensity-weighted)
    cx: float = 0.0
    cy: float = 0.0

    # Photometric properties
    intensity_mean: float = 0.0
    intensity_peak: float = 0.0

    # AI confidence from the verifying backend (0.0 = classical fallback)
    ai_confidence: float = 0.0

    # Descriptor tag identifying the backend that produced this candidate
    backend: str = "classical"          # "classical" | "yolo"


@dataclass
class PerceptionResult:
    """Output of one call to PerceptionInterface.run()."""
    candidates: List[Candidate] = field(default_factory=list)
    backend_used: str = "classical"     # "classical_cnn" | "yolo"
    frame_id: int = -1


@dataclass
class TargetIdentity:
    """
    The single designated target as selected by CandidateManager.

    Extends Candidate with temporal tracking state so that higher layers
    receive a stable, fused identity rather than a raw per-frame detection.
    """
    candidate: Optional[Candidate] = None

    # Temporal association
    temporal_id: int = -1              # Persistent track ID across frames
    history_frames: int = 0            # Consecutive frames this candidate was seen
    consecutive_misses: int = 0        # Frames without a matching detection

    # Fused quality metrics
    fused_confidence: float = 0.0      # Weighted combination of size + AI + history
    spatial_trajectory: List[Tuple[float, float]] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.candidate is not None and self.fused_confidence > 0.0


# ---------------------------------------------------------------------------
# 4.  Control contracts
# ---------------------------------------------------------------------------

@dataclass
class PATCommand:
    """
    Output of PATSupervisor — consumed by the actuator layer (ServoLoop).

    Decouples the PAT algorithm from the specific gimbal implementation so
    that the same command structure can drive Virtual, Replay, or Hardware
    actuators.
    """
    mode: str = "HOLD"                  # "VELOCITY" | "POSITION" | "HOLD" | "SEARCH"
    x: float = 0.0                     # Target x (position mode) or Vx (velocity mode)
    y: float = 0.0                     # Target y (position mode) or Vy (velocity mode)
    # PAT state label for logging
    pat_state: str = "IDLE"
    # Kalman-predicted position (always available for telemetry)
    kf_pred_x: float = 0.0
    kf_pred_y: float = 0.0


# ---------------------------------------------------------------------------
# 5.  Hardware abstraction Protocols
# ---------------------------------------------------------------------------

class CameraSource(abc.ABC):
    """
    Protocol for any frame source — Synthetic, Video, or Real camera.

    The PAT perception pipeline calls only capture_frame(); it never needs
    to know whether the frame comes from a simulated beacon, a pre-recorded
    clip, or a live sensor.
    """

    @abc.abstractmethod
    def capture_frame(self) -> np.ndarray:
        """Return a single uint8 grayscale frame (H × W)."""
        ...

    @property
    @abc.abstractmethod
    def frame_width(self) -> int: ...

    @property
    @abc.abstractmethod
    def frame_height(self) -> int: ...

    def is_available(self) -> bool:
        """Override to indicate whether the source can provide frames."""
        return True


class GimbalActuator(abc.ABC):
    """
    Protocol for any gimbal driver — Virtual, Replay, or Hardware adapter.

    The PAT controller calls only command_velocity / command_position; it
    never depends on the specific gimbal implementation.
    """

    @abc.abstractmethod
    def command_velocity(self, vx: float, vy: float) -> None: ...

    @abc.abstractmethod
    def command_position(self, px: float, py: float) -> None: ...

    @abc.abstractmethod
    def get_position(self) -> Tuple[float, float]: ...

    def hold(self) -> None:
        """Hold current position (default: no-op — subclasses may override)."""
        pass


class PerceptionBackend(abc.ABC):
    """
    Protocol for a perception backend (ClassicalAI or YOLO).

    Accepts a raw grayscale frame and returns a PerceptionResult.
    """

    @abc.abstractmethod
    def run(self, frame: np.ndarray, frame_id: int = -1) -> PerceptionResult: ...
