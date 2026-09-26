import numpy as np
from typing import Tuple

class World:
    """
    Represents the 2D coordinate space of the simulation.
    """
    def __init__(self, width: int = 2000, height: int = 2000):
        self.width = width
        self.height = height
        
        # We can maintain a base image if needed, for now it's conceptually an empty space
        # where the beacon is drawn dynamically based on state.
        
    def get_bounds(self) -> Tuple[int, int]:
        return (self.width, self.height)
    
    def is_within_bounds(self, x: float, y: float) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height
