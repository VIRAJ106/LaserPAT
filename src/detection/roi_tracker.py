"""
roi_tracker.py — Region-Of-Interest (ROI) tracker using OpenCV-based
centroid + bounding box propagation.

Manages a rolling predicted-ROI so the detector searches within a smaller
window when the beacon is being tracked, dramatically reducing false-positive
candidate rate in noisy/fog conditions.
"""
import numpy as np
import cv2
from typing import Optional, Tuple


class ROITracker:
    """
    Lightweight ROI manager that wraps around the Kalman predicted position.

    On each frame:
    1. `predict(kf_x, kf_y)` — given a Kalman-predicted world-space position
       and the current gimbal offset, computes the expected pixel ROI.
    2. `get_roi()` — returns (x1, y1, x2, y2) clip-coords for the current frame.
    3. `reset()` — called on LOST / SEARCH transitions.
    """

    def __init__(self, roi_half: int = 40, frame_shape: Tuple[int, int] = (480, 640)):
        """
        Args:
            roi_half   : Half-size of the square ROI in pixels.
            frame_shape: (height, width) of the camera frame.
        """
        self.roi_half = roi_half
        self.frame_h, self.frame_w = frame_shape
        self._cx: Optional[float] = None
        self._cy: Optional[float] = None
        self._active = False

    def predict(self, cam_cx: float, cam_cy: float) -> None:
        """
        Update ROI centre given the Kalman-predicted centroid in **pixel** coords
        (already projected from world-space by the caller).

        Args:
            cam_cx, cam_cy: Pixel coordinates of predicted beacon in current frame.
        """
        self._cx = float(cam_cx)
        self._cy = float(cam_cy)
        self._active = True

    def get_roi(self) -> Optional[Tuple[int, int, int, int]]:
        """
        Returns the ROI bounding box `(x1, y1, x2, y2)` clamped to frame bounds,
        or `None` if the tracker is inactive (SEARCH / LOST state).
        """
        if not self._active or self._cx is None:
            return None
        x1 = max(0, int(self._cx) - self.roi_half)
        y1 = max(0, int(self._cy) - self.roi_half)
        x2 = min(self.frame_w, int(self._cx) + self.roi_half)
        y2 = min(self.frame_h, int(self._cy) + self.roi_half)
        return (x1, y1, x2, y2)

    def apply_to_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        Crops and returns the ROI sub-image for further processing,
        or returns the full frame if ROI is inactive.
        """
        roi = self.get_roi()
        if roi is None:
            return frame
        x1, y1, x2, y2 = roi
        return frame[y1:y2, x1:x2]

    def draw_roi(self, frame: np.ndarray, color: Tuple[int, int, int] = (255, 165, 0)) -> None:
        """Draw ROI rectangle on an BGR display frame (in-place)."""
        roi = self.get_roi()
        if roi is not None:
            x1, y1, x2, y2 = roi
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1)

    def reset(self) -> None:
        self._cx = None
        self._cy = None
        self._active = False
