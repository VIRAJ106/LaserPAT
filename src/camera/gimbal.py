import numpy as np
from typing import Tuple

class Gimbal:
    """
    Simulates Pan-Tilt mechanics with rate and acceleration limits.
    Angles are kept conceptually simple (assuming 1 pixel = 1 unit of angle for small FOV approximation, 
    or we can map pixels to degrees).
    The specification notes FOV is 4x3 deg over 640x480 pixels => 109 urad/px.
    For simplicity in the 2D world:
    World is 2000x2000 pixels. We track the center of the camera viewport in world coordinates.
    Rate limits (5 deg/s) need to be converted to pixels/frame.
    4 deg = 640 px => 1 deg = 160 px.
    5 deg/s = 800 px/s. At 30 FPS, max rate is ~26.6 px/frame.
    """
    def __init__(self, start_x: float, start_y: float, max_rate_deg_s: float = 5.0, fps: float = 30.0,
                 world_bounds: tuple = None, fov_size: tuple = (640, 480), fov_deg: tuple = (4.0, 3.0)):
        self.x = start_x
        self.y = start_y

        self.fps = fps
        # Conversion: px_per_deg derived from config (fov_size[0] px / fov_deg[0] deg)
        # Previously hardcoded to 640/4.0 — now driven by YAML camera.fov_deg
        self.px_per_deg = fov_size[0] / fov_deg[0]
        
        # Max velocity in px/frame
        max_rate_px_s = max_rate_deg_s * self.px_per_deg
        self.max_v_px_frame = max_rate_px_s / fps
        
        # NEW: World bounds and FOV size for clamping
        self.world_bounds = world_bounds  # (width, height)
        self.fov_w, self.fov_h = fov_size
        
    def _clamp_to_world(self):
        """Clamp gimbal position so FOV stays within world bounds."""
        if self.world_bounds:
            world_w, world_h = self.world_bounds
            # Gimbal must stay within [fov_w/2, world_w - fov_w/2]
            # So FOV extends [0, world_w] when centered at edges
            self.x = max(self.fov_w / 2, min(world_w - self.fov_w / 2, self.x))
            self.y = max(self.fov_h / 2, min(world_h - self.fov_h / 2, self.y))
        
    def command_velocity(self, vx_px_frame: float, vy_px_frame: float):
        """
        Apply velocity command, subject to rate limits.
        """
        # Clamp velocities
        vx = max(-self.max_v_px_frame, min(self.max_v_px_frame, vx_px_frame))
        vy = max(-self.max_v_px_frame, min(self.max_v_px_frame, vy_px_frame))
        
        self.x += vx
        self.y += vy
        
        # NEW: Clamp to world bounds
        self._clamp_to_world()
        
    def command_position(self, target_x: float, target_y: float, snap: bool = False):
        """
        Slew towards a target position at max speed. Used during acquisition.
        If snap is True, instantly jump to the target position.
        """
        if snap:
            self.x = target_x
            self.y = target_y
            self._clamp_to_world()
            return

        dx = target_x - self.x
        dy = target_y - self.y
        dist = np.hypot(dx, dy)
        
        if dist > 0:
            vx = (dx / dist) * self.max_v_px_frame
            vy = (dy / dist) * self.max_v_px_frame
            
            # If the distance is smaller than what we'd cover in one frame, just snap to it
            if dist < self.max_v_px_frame:
                self.x = target_x
                self.y = target_y
            else:
                self.x += vx
                self.y += vy
        
        # NEW: Clamp to world bounds
        self._clamp_to_world()

    def get_position(self) -> Tuple[float, float]:
        return (self.x, self.y)
