"""
camera_source.py — CameraSource protocol implementations.

Architecture
------------
    CameraSource (abstract)
        ├── SyntheticCameraSource   ← wraps Sensor + Beacon.draw()
        └── VideoCameraSource       ← wraps cv2.VideoCapture

Both expose exactly the same capture_frame() → np.ndarray interface, so
the perception pipeline in scenario_runner.py and video_runner.py can share
identical code paths.

This fixes the architectural gap where video_runner.py and scenario_runner.py
had independently duplicated the detection loop without a shared source contract.
"""

from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from src.interfaces import CameraSource


# ---------------------------------------------------------------------------
# Synthetic camera (simulation world → rendered frame)
# ---------------------------------------------------------------------------

class SyntheticCameraSource(CameraSource):
    """
    Camera source backed by the simulation world.

    Wraps the existing Sensor + Viewport + Gimbal + Beacon pipeline and
    returns a raw (pre-disturbance) grayscale frame each call.

    The DisturbanceModel applies noise *after* capture_frame() returns, so
    this class is responsible only for the clean geometric render.

    Parameters
    ----------
    sensor : Sensor
        The camera.sensor.Sensor object (holds Viewport + Gimbal references).
    beacon : Beacon
        Primary target beacon.
    distractors : list[Beacon], optional
        Additional distractor beacons rendered into the same frame.
    """

    def __init__(self, sensor, beacon, distractors=None):
        self._sensor = sensor
        self._beacon = beacon
        self._distractors: list = distractors or []

    # -- CameraSource interface --

    def capture_frame(self) -> np.ndarray:
        """Render one synthetic grayscale frame from the current world state."""
        # Use the existing Sensor.capture_frame path for the primary beacon
        frame = self._sensor.capture_frame(self._beacon)

        # Draw any distractor beacons directly on top
        if self._distractors:
            cam_x, cam_y = self._sensor.gimbal.get_position()
            left, _, top, _ = self._sensor.viewport.get_bounds(cam_x, cam_y)
            for dist in self._distractors:
                dist.draw(frame, offset_x=left, offset_y=top)

        return frame

    @property
    def frame_width(self) -> int:
        return self._sensor.viewport.width

    @property
    def frame_height(self) -> int:
        return self._sensor.viewport.height


# ---------------------------------------------------------------------------
# Video camera (pre-recorded clip → frame)
# ---------------------------------------------------------------------------

class VideoCameraSource(CameraSource):
    """
    Camera source backed by a pre-recorded video file (.mp4 / .avi).

    Replaces the ad-hoc VideoCapture management previously embedded in
    video_runner.py.  The same perception pipeline code that runs in
    scenario_runner.py can now operate on real video without modification.

    Parameters
    ----------
    video_path : str
        Path to the video file.
    grayscale : bool
        If True (default), frames are converted to single-channel uint8
        before returning — matching the synthetic source output format.
    """

    def __init__(self, video_path: str, grayscale: bool = True):
        self._path = video_path
        self._grayscale = grayscale
        self._cap = cv2.VideoCapture(video_path)
        if not self._cap.isOpened():
            raise FileNotFoundError(f"Cannot open video: {video_path!r}")

        self._fps: float = self._cap.get(cv2.CAP_PROP_FPS) or 30.0
        self._total_frames: int = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self._w: int = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self._h: int = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._exhausted: bool = False

    # -- CameraSource interface --

    def capture_frame(self) -> Optional[np.ndarray]:
        """
        Read the next frame from the video file.

        Returns None (and sets is_available() → False) when the clip ends.
        """
        if self._exhausted:
            return None
        ret, bgr = self._cap.read()
        if not ret:
            self._exhausted = True
            return None
        return _to_grayscale(bgr) if self._grayscale else bgr

    def is_available(self) -> bool:
        return not self._exhausted

    @property
    def frame_width(self) -> int:
        return self._w

    @property
    def frame_height(self) -> int:
        return self._h

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def total_frames(self) -> int:
        return self._total_frames

    def release(self) -> None:
        """Release the underlying VideoCapture resource."""
        self._cap.release()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.release()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_grayscale(frame: np.ndarray) -> np.ndarray:
    """Convert BGR / BGRA / already-gray frame to uint8 H×W array."""
    if frame.ndim == 2:
        return frame
    if frame.shape[2] == 4:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
