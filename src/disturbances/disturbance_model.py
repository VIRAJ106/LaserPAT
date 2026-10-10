"""
disturbance_model.py — Unified causal disturbance propagation model.

Architecture
------------
    Physics / Environment
           ↓
    DisturbanceState (one object per frame)
           ↓
    ┌──────────────────────────────────┐
    │ platform_tx / platform_ty        │  ← from platform mechanical vibration
    │ platform_roll_rad                │  ← stub, ready for 6-DoF upgrade
    │ optical_blur_sigma_px            │  ← from Cn² turbulence model
    │ beam_wander_px                   │  ← from Cn² beam wander estimate
    │ sensor_gaussian_sigma            │  ← config override or Cn²-derived
    │ sensor_poisson / sensor_sp       │  ← from weather preset
    │ atmospheric_transmittance        │  ← Beer-Lambert (attenuation.py)
    └──────────────────────────────────┘
           ↓
    apply_to_frame()  →  disturbed sensor image

Replaces the previous independent generators:
  - disturbances/jitter.py   (still importable for legacy callers)
  - disturbances/noise.py    (still importable for legacy callers)
  - disturbances/weather.py  (still importable for legacy callers)
  - Platform.jitter_max_px   (now mediated through DisturbanceModel)
"""

from __future__ import annotations

import numpy as np

from src.interfaces import DisturbanceState
from src.disturbances.noise import (
    add_gaussian_noise,
    add_poisson_noise,
    add_salt_and_pepper_noise,
)
from src.disturbances.weather import WEATHER_PRESETS
from src.physics.attenuation import (
    get_gamma_for_weather,
    compute_transmittance,
    apply_weather_degradation,
)


class DisturbanceModel:
    """
    Single, authoritative disturbance model for the LaserPAT simulation.

    Aggregates all sources of disturbance into one DisturbanceState per
    simulation step so that higher-level modules can reason about the full
    noise budget, not just individual generators.

    Parameters
    ----------
    cfg : AppConfig
        The loaded YAML configuration.  The model reads from
        cfg.disturbances, cfg.turbulence (TurbulenceModel), and
        cfg.camera.
    link_distance_km : float
        Nominal link distance used for Cn²→sigma derivations.
        Default: 1.0 km (matching the SIH benchmark).
    """

    def __init__(self, cfg, link_distance_km: float = 1.0):
        self._cfg = cfg
        self._dist = cfg.disturbances
        self._cam  = cfg.camera
        self._turbulence = cfg.turbulence  # TurbulenceModel already built in config.py
        self._link_km = link_distance_km

        # Pre-compute weather transmittance (constant across a scenario run)
        gamma = get_gamma_for_weather(self._dist.weather_preset)
        self._tau = compute_transmittance(gamma, link_distance_km)
        self._ambient = (
            20 if self._dist.weather_preset not in ("clear", "low_light") else 0
        )

        # Pre-compute the sensor noise params from config (Cn² already applied
        # by config.py's late-binding when derive_from_cn2 is True)
        self._base_gaussian_sigma = self._dist.gaussian_sigma
        self._poisson             = self._dist.poisson
        self._sp_percent          = self._dist.salt_and_pepper_percent

        # Jitter amplitude from config
        self._jitter_max_px = self._dist.max_displacement_px

        # Cn² beam-wander estimate (scaled to pixels)
        # Only apply if derive_from_cn2 is enabled — otherwise use explicit sigma
        pixels_per_deg = self._cam.resolution[0] / self._cam.fov_deg[0]
        derive = getattr(self._dist, 'derive_from_cn2', True)
        if derive:
            try:
                self._beam_wander_px = self._turbulence.image_domain_sigma(
                    distance_km=link_distance_km,
                    pixels_per_deg=pixels_per_deg,
                    max_sigma_px=20.0,
                )
            except Exception:
                self._beam_wander_px = 0.0
        else:
            # derive_from_cn2 disabled: no turbulence blur beyond sensor noise
            self._beam_wander_px = 0.0


    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def step(self, platform=None) -> DisturbanceState:
        """
        Compute the DisturbanceState for the current simulation frame.

        The causal chain is:
            platform motion → mechanical jitter
            Cn² + geometry   → optical turbulence sigma
            weather preset  → atmospheric transmittance + sensor noise floor

        Parameters
        ----------
        platform : Platform | None
            If provided, the platform's current motion state modulates the
            mechanical jitter amplitude (moving platforms jitter more).

        Returns
        -------
        DisturbanceState
            One frozen snapshot of every active disturbance this frame.
        """
        # --- 1. Platform mechanical jitter --------------------------------
        jitter_active = self._jitter_max_px > 0
        if platform is not None and jitter_active:
            # Only add mechanical jitter if platform is actually moving
            if not _platform_is_moving(platform):
                jitter_active = False

        if jitter_active:
            tx = float(self._cfg.rng.uniform(-self._jitter_max_px, self._jitter_max_px))
            ty = float(self._cfg.rng.uniform(-self._jitter_max_px, self._jitter_max_px))
        else:
            tx, ty = 0.0, 0.0

        # --- 2. Optical / sensor noise ------------------------------------
        return DisturbanceState(
            platform_tx_px=tx,
            platform_ty_px=ty,
            platform_roll_rad=0.0,           # Stub — 6-DoF upgrade entry point

            optical_blur_sigma_px=self._beam_wander_px,
            beam_wander_px=self._beam_wander_px,

            sensor_gaussian_sigma=self._base_gaussian_sigma,
            sensor_poisson=self._poisson,
            sensor_sp_percent=self._sp_percent,

            atmospheric_transmittance=self._tau,
            weather_preset=self._dist.weather_preset,
        )

    def apply_to_frame(self, raw_frame: np.ndarray,
                       state: DisturbanceState) -> np.ndarray:
        """
        Apply the full disturbance chain to a raw sensor frame.

        Execution order (matches physical propagation):
          1. Atmospheric attenuation  (Beer-Lambert transmittance)
          2. Optical turbulence blur  (Gaussian PSF from Cn²)
          3. Sensor noise             (Poisson → Gaussian → S&P)

        Parameters
        ----------
        raw_frame : np.ndarray  uint8 H×W grayscale
        state : DisturbanceState  output of self.step()

        Returns
        -------
        np.ndarray  uint8 H×W disturbed grayscale frame
        """
        # 1. Atmospheric attenuation
        img = raw_frame.astype(np.float32) * state.atmospheric_transmittance
        img = img + state_ambient(state)
        img = np.clip(img, 0, 255).astype(np.uint8)

        # 2. Optical turbulence PSF (Gaussian blur if sigma > 0)
        if state.optical_blur_sigma_px > 0.5:
            import cv2
            ksize = max(3, int(state.optical_blur_sigma_px * 4) | 1)  # must be odd
            img = cv2.GaussianBlur(img, (ksize, ksize), state.optical_blur_sigma_px)

        # 3. Sensor noise stack
        if state.sensor_poisson:
            img = add_poisson_noise(img, self._cfg.rng)
        if state.sensor_gaussian_sigma > 0:
            img = add_gaussian_noise(img, state.sensor_gaussian_sigma, self._cfg.rng)
        if state.sensor_sp_percent > 0:
            img = add_salt_and_pepper_noise(img, state.sensor_sp_percent, self._cfg.rng)

        return img


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _platform_is_moving(platform) -> bool:
    """Return True if the platform motion model has a non-trivial velocity."""
    if hasattr(platform, 'motion'):
        m = platform.motion
        if hasattr(m, 'speed') and m.speed > 0.001:
            return True
        if (hasattr(m, 'vx') and hasattr(m, 'vy') and
                (abs(m.vx) > 0.001 or abs(m.vy) > 0.001)):
            return True
    return False


def state_ambient(state: DisturbanceState) -> float:
    """Return the ambient light floor for a given weather preset."""
    return 20.0 if state.weather_preset not in ("clear", "low_light") else 0.0
