import numpy as np
from typing import Tuple
from src.environment.motion import MotionModel

class Platform:
    """
    Simulates the motion of the FSOC terminal itself (jitter, drift).
    """
    def __init__(self, motion_model: MotionModel, jitter_max_px: float = 0.0, rng: np.random.Generator = None):
        self.motion = motion_model
        self.x, self.y = motion_model.x, motion_model.y
        self.jitter_max_px = jitter_max_px
        self._rng = rng if rng is not None else np.random.default_rng()

    def step(self, dt: float = 1.0) -> Tuple[float, float]:
        base_x, base_y = self.motion.step(dt)
        
        # Mechanical jitter is independent of platform translational motion.
        # Vibration sources (fans, electronics, structural resonance) exist
        # even when platform is stationary.
        if self.jitter_max_px > 0:
            jx = self._rng.uniform(-self.jitter_max_px, self.jitter_max_px)
            jy = self._rng.uniform(-self.jitter_max_px, self.jitter_max_px)
            self.x = base_x + jx
            self.y = base_y + jy
        else:
            self.x = base_x
            self.y = base_y
            
        return self.x, self.y
