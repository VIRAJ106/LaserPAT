class PIDController:
    """
    PID controller with anti-windup and derivative low-pass filter for gimbal control.
    Computes velocity commands based on position error.

    The derivative term uses an exponential moving-average filter (alpha) to
    suppress the large "derivative kick" that occurs when tracking error jumps
    suddenly (e.g. random-walk target, platform jitter).  Lower alpha = smoother
    derivative but slower response.
    """
    def __init__(self, kp: float, ki: float, kd: float, max_output: float,
                 dt: float = 1.0/30.0, derivative_alpha: float = 0.7):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.max_output = max_output
        self.dt = dt
        self.derivative_alpha = derivative_alpha  # EMA filter coefficient

        self.integral = 0.0
        self.prev_error = 0.0
        self._filtered_deriv = 0.0  # EMA state

    def reset(self):
        self.integral = 0.0
        self.prev_error = 0.0
        self._filtered_deriv = 0.0

    def compute(self, error: float) -> float:
        dt = max(self.dt, 1e-6)  # Guard against zero dt

        # Proportional
        p = self.kp * error

        # Integral with accumulation
        self.integral += error * dt
        i = self.ki * self.integral

        # Derivative with EMA low-pass filter to suppress kick on step errors
        raw_deriv = (error - self.prev_error) / dt
        self._filtered_deriv = (self.derivative_alpha * raw_deriv
                                + (1.0 - self.derivative_alpha) * self._filtered_deriv)
        d = self.kd * self._filtered_deriv
        self.prev_error = error

        output = p + i + d

        # Anti-windup: back-calculate integral to prevent windup
        if output > self.max_output:
            output = self.max_output
            if self.ki > 0:
                self.integral = (self.max_output - p - d) / self.ki
        elif output < -self.max_output:
            output = -self.max_output
            if self.ki > 0:
                self.integral = (-self.max_output - p - d) / self.ki

        return output
