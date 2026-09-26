import numpy as np
from typing import Tuple

class World:
    """
    Represents the 3D coordinate space of the simulation.
    While the sensor view is a 2D projection, the simulation fundamentally 
    models a 3D spatial volume (width, height, depth) to support accurate 
    WebGL/OpenGL representation and isometric projection.
    """
    def __init__(self, width: int = 2000, height: int = 2000, depth: int = 2000):
        self.width = width
        self.height = height
        self.depth = depth
        
        # We can maintain a base image if needed, for now it's conceptually an empty space
        # where the beacon is drawn dynamically based on state.
        
    def get_bounds(self) -> Tuple[int, int]:
        """Returns 2D bounds for backwards compatibility with legacy planar sensors."""
        return (self.width, self.height)
        
    def get_bounds_3d(self) -> Tuple[int, int, int]:
        """Returns full 3D bounds (width, height, depth)."""
        return (self.width, self.height, self.depth)
    
    def is_within_bounds(self, x: float, y: float, z: float = 0.0) -> bool:
        return (0 <= x < self.width) and (0 <= y < self.height) and (0 <= z < self.depth)
