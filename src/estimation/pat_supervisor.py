"""
pat_supervisor.py — PAT Supervisor: the canonical PAT loop authority.

Architecture
------------
    TargetIdentity | None
           ↓
    PATSupervisor
      ├── KalmanFilterCV.predict()
      ├── KalmanFilterCV.update()    (if identity is not None)
      ├── StateMachine.update()
      ├── coarse_alignment_quality() → HandoffQualification
      └── build PAT command
           ↓
    PATCommand (mode, x, y, pat_state, kf_pred_x, kf_pred_y)
           ↓
    Actuator Layer (ServoLoop / GimbalActuator)

This is the clean boundary between the estimation / PAT logic and the
control / actuator layer.  Everything above PATSupervisor is "what do I see";
everything below is "what do I command".
"""

from __future__ import annotations

from typing import Optional, Tuple

from src.interfaces import PATCommand, TargetIdentity
from src.estimation.kalman import KalmanFilterCV
from src.estimation.state_machine import StateMachine, TrackingState
from src.control.pid import PIDController
from src.control.search_patterns import SpiralSearch, RasterSearch
from src.units import deg_to_px


class PATSupervisor:
    """
    Owns and coordinates the full PAT estimation + control pipeline.

    In the previous architecture this logic was scattered across lines 210–262
    of scenario_runner.py.  Encapsulating it here:

    1. Makes the estimation/control boundary explicit.
    2. Allows PATSupervisor to be unit-tested independently of the runner.
    3. Gives the coarse-to-fine handoff a natural home (see handoff.py).
    4. Feeds a clean PATCommand to any GimbalActuator implementation.

    Parameters
    ----------
    cfg : AppConfig
        Full scenario configuration (read-only after __init__).
    dt : float
        Simulation timestep in seconds (default: 1/30).
    """

    def __init__(self, cfg, dt: float = 1.0 / 30.0):
        self._cfg = cfg
        self._dt  = dt

        # Kalman filter
        self._kf = KalmanFilterCV(dt=dt)

        # PAT state machine
        self._sm = StateMachine(
            lock_threshold_px=cfg.estimation.lock_threshold_px,
            required_lock_frames=cfg.estimation.lock_frames,
        )

        # PID controllers (one per axis)
        px_per_deg = cfg.camera.resolution[0] / cfg.camera.fov_deg[0]
        max_v = deg_to_px(cfg.camera.gimbal.max_pan_rate_deg_s, px_per_deg) / 30.0   # px/frame

        self._pid_x = PIDController(cfg.control.kp, cfg.control.ki, cfg.control.kd, max_v, dt=dt)
        self._pid_y = PIDController(cfg.control.kp, cfg.control.ki, cfg.control.kd, max_v, dt=dt)
        self._max_v = max_v

        # Search patterns
        w, h = cfg.environment.world_size
        cx, cy = w / 2.0, h / 2.0

        self._spiral = SpiralSearch(
            cx, cy,
            fov_size=cfg.camera.resolution[1],
            world_bounds=tuple(cfg.environment.world_size),
            fov_dims=tuple(cfg.camera.resolution),
        )
        self._raster = RasterSearch(
            cx, cy,
            search_w=float(w) * 0.9,
            search_h=float(h) * 0.9,
            col_spacing=300.0,
            row_spacing=200.0,
            dwell_time=0.25,
            world_bounds=tuple(cfg.environment.world_size),
            fov_dims=tuple(cfg.camera.resolution),
        )

        # Search adaptation state
        self._spiral_time   = 0.0
        self._spiral_max_t  = 4.0
        self._use_raster    = False
        self._last_known_x  = cx
        self._last_known_y  = cy

        # Cumulative lock duration (for handoff qualification)
        self._lock_frames: int = 0

        # Start in SEARCH state immediately
        self._sm.start_search()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def step(
        self,
        identity: Optional[TargetIdentity],
        gimbal_x: float,
        gimbal_y: float,
    ) -> PATCommand:
        """
        Advance the PAT supervisor by one simulation step.

        Parameters
        ----------
        identity : TargetIdentity | None
            Output of CandidateManager.update() for the current frame.
        gimbal_x, gimbal_y : float
            Current gimbal centre in world coordinates (needed by PID).

        Returns
        -------
        PATCommand
            The command to be executed by the actuator this frame.
        """
        # --- Kalman prediction ---
        self._kf.predict()

        # --- Measurement update ---
        valid = False
        euclidean_error = float('inf')
        gate_passed = True

        if identity is not None and identity.is_valid:
            cx = identity.candidate.cx
            cy = identity.candidate.cy
            gate_passed = self._kf.update(cx, cy)
            valid = gate_passed
            if valid:
                kf_x, kf_y = self._kf.get_position()
                euclidean_error = ((cx - kf_x) ** 2 + (cy - kf_y) ** 2) ** 0.5

        valid_and_gated = valid and gate_passed

        # --- State machine ---
        state = self._sm.update(valid_and_gated, euclidean_error)

        # --- Lock duration accumulator (for handoff) ---
        if state == TrackingState.LOCKED:
            self._lock_frames += 1
        else:
            self._lock_frames = 0

        # --- Build command ---
        cmd = self._build_command(state, gimbal_x, gimbal_y)
        return cmd

    def start_search(self) -> None:
        """Transition to SEARCH state (call at scenario start)."""
        self._sm.start_search()

    def reset(self) -> None:
        """Full reset — use when restarting a scenario."""
        self._kf.reset()
        self._sm.reset()
        self._pid_x = PIDController(
            self._cfg.control.kp, self._cfg.control.ki, self._cfg.control.kd,
            self._max_v, dt=self._dt
        )
        self._pid_y = PIDController(
            self._cfg.control.kp, self._cfg.control.ki, self._cfg.control.kd,
            self._max_v, dt=self._dt
        )
        self._spiral_time  = 0.0
        self._use_raster   = False
        self._lock_frames  = 0

    # Properties for handoff / telemetry
    @property
    def kf(self) -> KalmanFilterCV:
        return self._kf

    @property
    def state(self) -> TrackingState:
        return self._sm.state

    @property
    def lock_frames(self) -> int:
        """Number of consecutive LOCKED frames — key handoff qualification input."""
        return self._lock_frames

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_command(
        self, state: TrackingState, gimbal_x: float, gimbal_y: float
    ) -> PATCommand:
        kf_x, kf_y = self._kf.get_position()
        kv_x, kv_y = self._kf.get_velocity()

        if state == TrackingState.SEARCH:
            self._spiral_time += self._dt
            if self._spiral_time > self._spiral_max_t and not self._use_raster:
                self._use_raster = True
                self._raster.reset(self._last_known_x, self._last_known_y)

            sx, sy = (
                self._raster.step(self._dt) if self._use_raster
                else self._spiral.step(self._dt)
            )
            return PATCommand(
                mode="POSITION", x=sx, y=sy,
                pat_state=state.name,
                kf_pred_x=kf_x, kf_pred_y=kf_y,
            )

        elif state == TrackingState.REACQUIRE:
            # Slew to KF predicted position + reset search for next cycle
            self._last_known_x, self._last_known_y = kf_x, kf_y
            self._spiral_time = 0.0
            self._use_raster  = False
            self._spiral.reset(kf_x, kf_y)

            err_x = kf_x - gimbal_x
            err_y = kf_y - gimbal_y
            vx = self._pid_x.compute(err_x) + kv_x * self._dt
            vy = self._pid_y.compute(err_y) + kv_y * self._dt
            return PATCommand(
                mode="VELOCITY", x=vx, y=vy,
                pat_state=state.name,
                kf_pred_x=kf_x, kf_pred_y=kf_y,
            )

        else:  # ACQUIRE / LOCKED / COAST
            self._last_known_x, self._last_known_y = gimbal_x, gimbal_y
            self._spiral_time = 0.0
            self._use_raster  = False
            self._spiral.reset(gimbal_x, gimbal_y)

            err_x = kf_x - gimbal_x
            err_y = kf_y - gimbal_y
            vx = self._pid_x.compute(err_x) + kv_x * self._dt
            vy = self._pid_y.compute(err_y) + kv_y * self._dt
            return PATCommand(
                mode="VELOCITY", x=vx, y=vy,
                pat_state=state.name,
                kf_pred_x=kf_x, kf_pred_y=kf_y,
            )
