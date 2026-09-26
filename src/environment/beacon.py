import cv2
import numpy as np
from typing import Tuple
from src.environment.motion import MotionModel

class Beacon:
    def __init__(self, shape: str, size: Tuple[int, int], motion_model: MotionModel):
        self.shape = shape  # "square" or "gaussian"
        self.w, self.h = size
        self.motion = motion_model
        self.x, self.y = motion_model.x, motion_model.y

    def step(self, dt: float = 1.0) -> Tuple[float, float]:
        self.x, self.y = self.motion.step(dt)
        return self.x, self.y

    def draw(self, image: np.ndarray, offset_x: float, offset_y: float):
        """
        Draws the beacon on the given image patch (e.g. camera viewport).
        offset_x, offset_y are the top-left coordinates of the viewport in the world.
        """
        draw_x = int(round(self.x - offset_x))
        draw_y = int(round(self.y - offset_y))
        
        # Check if beacon center is anywhere near the viewport bounds
        img_h, img_w = image.shape
        if not (-self.w < draw_x < img_w + self.w and -self.h < draw_y < img_h + self.h):
            return
            
        if self.shape == "square":
            top_left = (max(0, draw_x - self.w // 2), max(0, draw_y - self.h // 2))
            bottom_right = (min(img_w, draw_x + self.w // 2), min(img_h, draw_y + self.h // 2))
            
            # Simple binary box for now, max intensity 255
            if top_left[0] < bottom_right[0] and top_left[1] < bottom_right[1]:
                image[top_left[1]:bottom_right[1], top_left[0]:bottom_right[0]] = 255
                
        elif self.shape == "gaussian":
            # Draw a 2D Gaussian spot
            sigma_x = self.w / 4.0
            sigma_y = self.h / 4.0
            # For performance, only compute over a small bounding box
            box_size = max(self.w, self.h) * 2
            x_min = max(0, draw_x - box_size)
            x_max = min(img_w, draw_x + box_size)
            y_min = max(0, draw_y - box_size)
            y_max = min(img_h, draw_y + box_size)
            
            if x_min < x_max and y_min < y_max:
                Y, X = np.ogrid[y_min:y_max, x_min:x_max]
                dist = ((X - draw_x)**2) / (2 * sigma_x**2) + ((Y - draw_y)**2) / (2 * sigma_y**2)
                gaussian = np.exp(-dist) * 255
                # Add to existing image (clipping to 255)
                patch = image[y_min:y_max, x_min:x_max].astype(np.uint16) + gaussian.astype(np.uint16)
                image[y_min:y_max, x_min:x_max] = np.clip(patch, 0, 255).astype(np.uint8)
