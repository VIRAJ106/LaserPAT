import pytest
import numpy as np
from src.camera.gimbal import Gimbal
from src.camera.viewport import Viewport

def test_gimbal_rate_limits():
    """
    Test that the gimbal strictly obeys the 5 deg/s rate limits.
    5 deg/s at 30 FPS with 160 px/deg = 26.666 px/frame.
    """
    gimbal = Gimbal(start_x=1000.0, start_y=1000.0, max_rate_deg_s=5.0, fps=30.0)
    
    # Try to command a massive velocity
    gimbal.command_velocity(vx_px_frame=100.0, vy_px_frame=100.0)
    
    x, y = gimbal.get_position()
    assert np.isclose(x, 1000.0 + 26.666, atol=0.1)
    assert np.isclose(y, 1000.0 + 26.666, atol=0.1)
    
def test_gimbal_slew():
    gimbal = Gimbal(start_x=1000.0, start_y=1000.0, max_rate_deg_s=5.0, fps=30.0)
    
    # Target is far away, should move at max speed
    gimbal.command_position(target_x=1500.0, target_y=1000.0)
    x, y = gimbal.get_position()
    assert np.isclose(x, 1000.0 + 26.666, atol=0.1)
    assert np.isclose(y, 1000.0, atol=0.1)
    
    # Target is close, should snap exactly to target
    gimbal.command_position(target_x=1000.0 + 26.666 + 10.0, target_y=1000.0)
    x, y = gimbal.get_position()
    assert np.isclose(x, 1000.0 + 26.666 + 10.0, atol=0.1)

def test_viewport_extraction():
    vp = Viewport(width=640, height=480)
    left, right, top, bottom = vp.get_bounds(center_x=1000.0, center_y=1000.0)
    
    assert left == 1000.0 - 320.0
    assert right == 1000.0 + 320.0
    assert top == 1000.0 - 240.0
    assert bottom == 1000.0 + 240.0
