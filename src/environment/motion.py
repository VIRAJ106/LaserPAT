import math
import numpy as np
from typing import Tuple

class MotionModel:
    def __init__(self, start_pos: Tuple[float, float], speed: float):
        self.x, self.y = start_pos
        self.speed = speed
        self.t = 0.0

    def step(self, dt: float = 1.0) -> Tuple[float, float]:
        self.t += dt
        return self._calculate_next(dt)
        
    def _calculate_next(self, dt: float) -> Tuple[float, float]:
        raise NotImplementedError

class StraightMotion(MotionModel):
    def __init__(self, start_pos: Tuple[float, float], speed: float, angle_rad: float = 0.0):
        super().__init__(start_pos, speed)
        self.angle = angle_rad
        self.vx = speed * math.cos(self.angle)
        self.vy = speed * math.sin(self.angle)

    def _calculate_next(self, dt: float) -> Tuple[float, float]:
        self.x += self.vx * dt
        self.y += self.vy * dt
        return (self.x, self.y)

class CircularMotion(MotionModel):
    def __init__(self, center: Tuple[float, float], radius: float, angular_speed: float, start_angle: float = 0.0):
        # We start at center + radius*cos(start_angle)
        start_x = center[0] + radius * math.cos(start_angle)
        start_y = center[1] + radius * math.sin(start_angle)
        super().__init__((start_x, start_y), angular_speed)
        self.cx, self.cy = center
        self.radius = radius
        self.omega = angular_speed
        self.angle = start_angle

    def _calculate_next(self, dt: float) -> Tuple[float, float]:
        self.angle += self.omega * dt
        self.x = self.cx + self.radius * math.cos(self.angle)
        self.y = self.cy + self.radius * math.sin(self.angle)
        return (self.x, self.y)

class Figure8Motion(MotionModel):
    def __init__(self, center: Tuple[float, float], width: float, height: float, speed: float):
        super().__init__(center, speed)
        self.cx, self.cy = center
        self.a = width / 2.0
        self.b = height / 2.0

    def _calculate_next(self, dt: float) -> Tuple[float, float]:
        # Lemniscate of Gerono parameterized by time
        self.x = self.cx + self.a * math.sin(self.speed * self.t)
        self.y = self.cy + self.b * math.sin(self.speed * self.t) * math.cos(self.speed * self.t)
        return (self.x, self.y)

class RandomWalkMotion(MotionModel):
    def __init__(self, start_pos: Tuple[float, float], max_step: float, world_bounds: Tuple[float, float] = (2000, 2000)):
        super().__init__(start_pos, max_step)
        self.world_w, self.world_h = world_bounds
        self.margin = 100  # Stay 100px away from edges for safety
        
    def _calculate_next(self, dt: float) -> Tuple[float, float]:
        # Random walk step
        self.x += np.random.uniform(-self.speed, self.speed)
        self.y += np.random.uniform(-self.speed, self.speed)
        
        # CRITICAL FIX: Bounce off boundaries (reflect motion)
        # Keep beacon within [margin, world_size - margin]
        if self.x < self.margin:
            self.x = self.margin + (self.margin - self.x)  # Reflect
        elif self.x > self.world_w - self.margin:
            self.x = (self.world_w - self.margin) - (self.x - (self.world_w - self.margin))
            
        if self.y < self.margin:
            self.y = self.margin + (self.margin - self.y)  # Reflect
        elif self.y > self.world_h - self.margin:
            self.y = (self.world_h - self.margin) - (self.y - (self.world_h - self.margin))
        
        # Final safety clamp
        self.x = max(self.margin, min(self.world_w - self.margin, self.x))
        self.y = max(self.margin, min(self.world_h - self.margin, self.y))
        
        return (self.x, self.y)
