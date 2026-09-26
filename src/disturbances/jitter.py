import numpy as np

def apply_jitter(position: tuple, sigma: float) -> tuple:
    """
    Applies Gaussian random walk jitter to simulate mechanical vibrations.
    
    Args:
        position (tuple): (x, y) starting position.
        sigma (float): Standard deviation of the jitter (pixels).
        
    Returns:
        tuple: (new_x, new_y) after applying jitter.
    """
    if sigma <= 0:
        return position
    dx = np.random.normal(0, sigma)
    dy = np.random.normal(0, sigma)
    return (position[0] + dx, position[1] + dy)
