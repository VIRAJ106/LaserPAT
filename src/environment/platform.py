import numpy as np
from typing import Tuple
from src.environment.motion import MotionModel

class Platform:
    """
    Simulates the motion of the FSOC terminal itself (jitter, drift).
    """
    def __init__(self, motion_model: MotionModel, jitter_max_px: float = 0.0):
        self.motion = motion_model
        self.x, self.y = motion_model.x, motion_model.y
        self.jitter_max_px = jitter_max_px

    def step(self, dt: float = 1.0) -> Tuple[float, float]:
        base_x, base_y = self.motion.step(dt)
        
        # NEW: Only add jitter if platform is actually moving
        # Check if motion model has meaningful speed (not just static)
        is_moving = False
        if hasattr(self.motion, 'speed') and self.motion.speed > 0.001:
            is_moving = True
        elif hasattr(self.motion, 'vx') and hasattr(self.motion, 'vy'):
            if abs(self.motion.vx) > 0.001 or abs(self.motion.vy) > 0.001:
                is_moving = True
        
        # Add high-frequency jitter ONLY when moving
        if self.jitter_max_px > 0 and is_moving:
            jx = np.random.uniform(-self.jitter_max_px, self.jitter_max_px)
            jy = np.random.uniform(-self.jitter_max_px, self.jitter_max_px)
            self.x = base_x + jx
            self.y = base_y + jy
        else:
            self.x = base_x
            self.y = base_y
            
        return self.x, self.y
