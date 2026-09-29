"""
handoff.py — Coarse-to-fine handoff qualification layer.

Architecture
------------
    PATSupervisor (lock quality state)
              +
    LinkBudgetModel (pointing loss → received power)
              ↓
    HandoffQualification
      ├── angular_error_urad   — pointing accuracy
      ├── lock_duration_frames — temporal stability
      ├── confidence           — KF covariance quality
      ├── los_rate_px_frame    — relative angular rate
      └── link_status          — "UP" / "DOWN" from link budget
              ↓
    HANDOFF DECISION (qualify / not ready)

Connecting PATSupervisor → LinkBudgetModel gives LaserPAT an FSOC-specific
architecture that no pure-2D tracker can claim:

"PAT lock quality is continuously evaluated against the pointing-loss model.
 Coarse handoff is only declared when the link budget shows positive margin."
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.estimation.pat_supervisor import PATSupervisor
    from src.physics.link_budget import LinkBudgetModel


@dataclass
class HandoffQualification:
    """
    Coarse-alignment quality snapshot for FSOC fine-pointing handoff.

    All fields are populated each simulation frame by evaluate_handoff().
    A handoff gate check compares them against operator-defined thresholds.
    """
    # Angular pointing accuracy
    angular_error_urad: float = 0.0

    # Temporal stability (consecutive LOCKED frames)
    lock_duration_frames: int = 0

    # KF confidence proxy (lower trace P → more confident)
    kf_uncertainty: float = 0.0

    # Angular rate of change of LOS (px/frame — high rate = hard to hand off)
    los_rate_px_frame: float = 0.0

    # Link budget output
    received_power_dBm: float = -999.0
    pointing_loss_dB: float = 0.0
    margin_dB: float = -999.0
    link_status: str = "DOWN"

    # PAT state at time of evaluation
    pat_state: str = "IDLE"

    @property
    def is_qualified(self) -> bool:
        """
        Conservative handoff qualification gate.

        Requires:
          • Link budget margin > 0 dB  (beam physically reaching receiver)
          • Lock held for ≥ 10 consecutive frames  (~0.33 s at 30 fps)
          • KF uncertainty (trace P) below threshold
          • Angular error below 500 µrad
        """
        return (
            self.link_status == "UP"
            and self.lock_duration_frames >= 10
            and self.angular_error_urad < 500.0
            and self.kf_uncertainty < 200.0
        )

    def to_dict(self) -> dict:
        return {
            "angular_error_urad":   round(self.angular_error_urad, 2),
            "lock_duration_frames": self.lock_duration_frames,
            "kf_uncertainty":       round(self.kf_uncertainty, 3),
            "los_rate_px_frame":    round(self.los_rate_px_frame, 3),
            "received_power_dBm":   round(self.received_power_dBm, 2),
            "pointing_loss_dB":     round(self.pointing_loss_dB, 2),
            "margin_dB":            round(self.margin_dB, 2),
            "link_status":          self.link_status,
            "pat_state":            self.pat_state,
            "qualified":            self.is_qualified,
        }


def evaluate_handoff(
    supervisor: "PATSupervisor",
    link: "LinkBudgetModel",
    tracking_error_px: float,
    fov_deg: float = 4.0,
    res_px: float = 640.0,
    distance_km: float = 1.0,
) -> HandoffQualification:
    """
    Evaluate coarse-to-fine handoff readiness for the current frame.

    Connects PATSupervisor lock quality metrics to the LinkBudgetModel
    so that the handoff decision is grounded in physical pointing loss.

    Parameters
    ----------
    supervisor : PATSupervisor
        Must be called *after* supervisor.step() for the current frame.
    link : LinkBudgetModel
        The instantiated link budget model (from cfg.link_budget_model).
    tracking_error_px : float
        Euclidean tracking error in sensor pixels this frame.
    fov_deg : float
        Horizontal FOV in degrees (for pixel → angle conversion).
    res_px : float
        Horizontal resolution in pixels.
    distance_km : float
        Nominal link distance for link budget computation.

    Returns
    -------
    HandoffQualification
    """
    # Convert pixel error → microradians
    px_per_deg = res_px / fov_deg
    if math.isfinite(tracking_error_px) and tracking_error_px >= 0:
        deg_error  = tracking_error_px / px_per_deg
        urad_error = math.radians(deg_error) * 1e6
    else:
        urad_error = float('inf')

    # Link budget
    if math.isfinite(tracking_error_px):
        budget = link.compute(
            distance_km=distance_km,
            pointing_error_px=tracking_error_px,
            fov_deg=fov_deg,
            res_px=res_px,
        )
    else:
        budget = {
            "pointing_error_urad": urad_error,
            "pointing_loss_dB": 999.0,
            "received_power_dBm": -999.0,
            "margin_dB": -999.0,
            "link_status": "DOWN",
        }

    # KF covariance trace as uncertainty proxy
    kf_uncertainty = supervisor.kf.get_covariance_trace()

    # LOS rate from KF velocity
    kv_x, kv_y = supervisor.kf.get_velocity()
    los_rate = math.hypot(kv_x, kv_y)

    return HandoffQualification(
        angular_error_urad   = urad_error,
        lock_duration_frames = supervisor.lock_frames,
        kf_uncertainty       = kf_uncertainty,
        los_rate_px_frame    = los_rate,
        received_power_dBm   = budget["received_power_dBm"],
        pointing_loss_dB     = budget["pointing_loss_dB"],
        margin_dB            = budget["margin_dB"],
        link_status          = budget["link_status"],
        pat_state            = supervisor.state.name,
    )
