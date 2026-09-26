import numpy as np
from typing import Tuple

class Viewport:
    """
    Extracts the FOV from the world and handles pixel conversion.
    """
    def __init__(self, width: int = 640, height: int = 480):
        self.width = width
        self.height = height

    def get_bounds(self, center_x: float, center_y: float) -> Tuple[float, float, float, float]:
        """
        Returns (left, right, top, bottom) in world coordinates.
        """
        left = center_x - self.width / 2.0
        right = center_x + self.width / 2.0
        top = center_y - self.height / 2.0
        bottom = center_y + self.height / 2.0
        return (left, right, top, bottom)
        
    def create_empty_frame(self) -> np.ndarray:
        """
        Creates an empty black frame for the camera viewport.
        """
        return np.zeros((self.height, self.width), dtype=np.uint8)
