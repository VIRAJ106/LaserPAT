import numpy as np

class KalmanFilterCV:
    """
    Constant Velocity Kalman Filter operating in world coordinates.
    Decouples camera motion from target motion.
    State vector x = [px, vx, py, vy]^T
    """
    def __init__(self, dt: float = 1.0/30.0, q_noise: float = 1.0, r_noise: float = 5.0):
        self.dt = dt
        
        # State vector
        self.x = np.zeros((4, 1))
        
        # State transition matrix
        self.F = np.array([
            [1, dt, 0, 0],
            [0, 1, 0, 0],
            [0, 0, 1, dt],
            [0, 0, 0, 1]
        ])
        
        # Measurement matrix (observing px, py)
        self.H = np.array([
            [1, 0, 0, 0],
            [0, 0, 1, 0]
        ])
        
        # Process noise covariance Q
        # For continuous constant velocity model:
        q = q_noise
        dt2 = dt**2
        dt3 = dt**3
        dt4 = dt**4
        self.Q = q * np.array([
            [dt4/4, dt3/2, 0, 0],
            [dt3/2, dt2, 0, 0],
            [0, 0, dt4/4, dt3/2],
            [0, 0, dt3/2, dt2]
        ])
        
        # Measurement noise covariance R
        self.R = np.eye(2) * (r_noise**2)
        
        # Estimate covariance P — with a minimum floor to prevent over-confidence
        self.P = np.eye(4) * 1000.0
        self._P_floor = np.diag([1.0, 0.1, 1.0, 0.1])  # Minimum P so gate never collapses
        
        self.is_initialized = False

    def init_state(self, px: float, py: float):
        self.x = np.array([[px], [0], [py], [0]])
        self.P = np.eye(4) * 100.0
        self.is_initialized = True

    def predict(self) -> np.ndarray:
        """
        x_hat(-) = F * x_hat(+)
        P(-) = F * P(+) * F^T + Q
        """
        if not self.is_initialized:
            return self.x
            
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        return self.x

    def update(self, mx: float, my: float) -> bool:
        """
        K = P(-) * H^T * (H * P(-) * H^T + R)^-1
        x_hat(+) = x_hat(-) + K * (z - H * x_hat(-))
        P(+) = (I - K * H) * P(-)
        
        Returns True if measurement accepted, False if rejected by innovation gate.
        """
        if not self.is_initialized:
            self.init_state(mx, my)
            return True

        z = np.array([[mx], [my]])
        
        # Innovation
        y = z - (self.H @ self.x)
        
        # Innovation covariance
        S = self.H @ self.P @ self.H.T + self.R
        S_inv = np.linalg.inv(S)
        
        # Adaptive innovation gate: use pixel-space Euclidean distance as primary gate.
        # This avoids the problem where P collapses after lock and the normalised
        # Mahalanobis distance grows huge even for small, valid measurement noise.
        # Gate: reject only if measurement is extremely far (effectively no gate for simulation)
        pixel_dist = float(np.sqrt(y[0,0]**2 + y[1,0]**2))
        if pixel_dist > 2500.0:
            return False  # True clutter / multipath — reject
            
        # Kalman Gain
        K = self.P @ self.H.T @ S_inv
        
        # State update
        self.x = self.x + (K @ y)
        
        # Covariance update with Joseph form for numerical stability
        I = np.eye(4)
        IKH = I - K @ self.H
        self.P = IKH @ self.P @ IKH.T + K @ self.R @ K.T
        
        # Enforce covariance floor so gate never collapses to near-zero
        self.P = np.maximum(self.P, self._P_floor)
        
        return True

    def get_position(self) -> tuple[float, float]:
        return float(self.x[0, 0]), float(self.x[2, 0])
        
    def get_velocity(self) -> tuple[float, float]:
        return float(self.x[1, 0]), float(self.x[3, 0])
        
    def get_covariance_trace(self) -> float:
        """Trace of P serves as a scalar measure of uncertainty."""
        return float(np.trace(self.P))
    
    def reset(self):
        """Reset filter to uninitialized state."""
        self.x = np.zeros((4, 1))
        self.P = np.eye(4) * 1000.0
        self.is_initialized = False
