import math
from typing import Tuple


class SpiralSearch:
    """
    Generates a blind Archimedean spiral search pattern starting from a given
    world-space position. Used as the primary SEARCH pattern.
    """
    def __init__(self, start_x: float, start_y: float, fov_size: float,
                 angular_speed: float = 5.0, world_bounds: tuple = None,
                 fov_dims: tuple = (640, 480)):
        self.start_x = start_x
        self.start_y = start_y
        self.fov_size = fov_size
        self.angular_speed = angular_speed
        self.t = 0.0
        self.world_bounds = world_bounds
        self.fov_w, self.fov_h = fov_dims
        # Spacing between turns — covers FOV width per full revolution
        self.b = (fov_size * 1.5) / (2 * math.pi)

    def step(self, dt: float) -> Tuple[float, float]:
        self.t += dt
        theta = self.angular_speed * self.t
        r = self.b * theta

        x = self.start_x + r * math.cos(theta)
        y = self.start_y + r * math.sin(theta)

        if self.world_bounds:
            world_w, world_h = self.world_bounds
            x = max(self.fov_w / 2, min(world_w - self.fov_w / 2, x))
            y = max(self.fov_h / 2, min(world_h - self.fov_h / 2, y))

        return float(x), float(y)

    def reset(self, start_x: float, start_y: float):
        """Reset the spiral to originate from the given world-space coordinate."""
        self.start_x = start_x
        self.start_y = start_y
        self.t = 0.0


class RasterSearch:
    """
    Continuous Raster (Boustrophedon) search pattern.
    Sweeps back and forth continuously without stopping, covering the entire
    search area smoothly.
    
    Args:
        start_x, start_y : World-space origin (centre of search area).
        search_w, search_h: Width/height of the rectangular area to cover.
        col_spacing      : Horizontal spacing (not used in continuous, kept for compatibility).
        row_spacing      : Vertical spacing between rows (px).
                           Should be ~50-70% of FOV height for overlap.
        dwell_time       : Re-purposed as sweep speed if needed (kept for compatibility).
        world_bounds     : (world_w, world_h) or None.
        fov_dims         : (fov_w, fov_h) for clamping.
    """

    def __init__(self, start_x: float, start_y: float,
                 search_w: float = 1600.0, search_h: float = 1600.0,
                 col_spacing: float = 300.0, row_spacing: float = 240.0,
                 dwell_time: float = 0.3,
                 world_bounds: tuple = None, fov_dims: tuple = (640, 480)):
        self.world_bounds = world_bounds
        self.fov_w, self.fov_h = fov_dims
        self.row_spacing = row_spacing
        
        # In continuous sweep, speed (px/sec) is roughly search_w / 2 seconds
        self.speed = 1000.0  # px per second
        
        self.start_x = start_x
        self.start_y = start_y
        self.search_w = search_w
        self.search_h = search_h
        
        self.t = 0.0

    def step(self, dt: float) -> Tuple[float, float]:
        self.t += dt
        
        # Time required to complete one row sweep
        row_time = self.search_w / self.speed
        
        if row_time <= 0:
            return float(self.start_x), float(self.start_y)
            
        row = int(self.t / row_time)
        progress = (self.t % row_time) / row_time
        
        # Calculate Y (move down row by row)
        # If we exceed max rows, we wrap around back to the top
        max_rows = max(1, int(self.search_h / self.row_spacing))
        current_row = row % max_rows
        
        y = self.start_y - (self.search_h / 2.0) + (current_row * self.row_spacing)
        
        # Calculate X (sweep right on even rows, left on odd rows)
        if current_row % 2 == 0:
            x = self.start_x - (self.search_w / 2.0) + (progress * self.search_w)
        else:
            x = self.start_x + (self.search_w / 2.0) - (progress * self.search_w)
            
        # Clamp to world bounds
        if self.world_bounds:
            ww, wh = self.world_bounds
            x = max(self.fov_w / 2, min(ww - self.fov_w / 2, x))
            y = max(self.fov_h / 2, min(wh - self.fov_h / 2, y))
            
        return float(x), float(y)

    def reset(self, start_x: float, start_y: float):
        """Reset raster search to sweep the full world view."""
        if self.world_bounds:
            self.start_x = self.world_bounds[0] / 2.0
            self.start_y = self.world_bounds[1] / 2.0
            self.search_w = self.world_bounds[0]
            self.search_h = self.world_bounds[1]
        else:
            self.start_x = start_x
            self.start_y = start_y
            self.search_w = 4000.0
            self.search_h = 4000.0
            
        self.t = 0.0
