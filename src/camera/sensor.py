import numpy as np
from src.camera.viewport import Viewport
from src.camera.gimbal import Gimbal
from src.environment.beacon import Beacon

class Sensor:
    """
    Integrates the Viewport and Gimbal to produce the final frame from the world state.
    """
    def __init__(self, viewport: Viewport, gimbal: Gimbal):
        self.viewport = viewport
        self.gimbal = gimbal
        
    def capture_frame(self, beacon: Beacon) -> np.ndarray:
        """
        Captures a 640x480 frame. Draws the beacon if it is within the FOV.
        """
        frame = self.viewport.create_empty_frame()
        
        # Current camera center in world coordinates
        cam_x, cam_y = self.gimbal.get_position()
        
        # Calculate the top-left offset of the viewport
        left, _, top, _ = self.viewport.get_bounds(cam_x, cam_y)
        
        # Draw beacon onto the frame (handles coordinate mapping internally)
        beacon.draw(frame, offset_x=left, offset_y=top)
        
        return frame
