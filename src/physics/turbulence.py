"""
turbulence.py — Cn²-based atmospheric turbulence parameter derivations.

Implements physically grounded transformations from the refractive-index
structure parameter (Cn²) to image-domain noise levels and coherence metrics.

References
----------
1. Andrews, L.C. & Phillips, R.L. (2005). *Laser Beam Propagation through
   Random Media*, 2nd ed. SPIE Press.  (Rytov variance, Chapter 5)
2. Hardy, J.W. (1998). *Adaptive Optics for Astronomical Telescopes*.
   Oxford University Press.  (Fried parameter r₀, Chapter 2)
3. Hufnagel, R.E. & Stanley, N.R. (1964). "Modulation Transfer Function
   associated with Image Transmission through Turbulent Media." JOSA 54(1).
   (Hufnagel-Valley Cn² altitude profile)

Usage
-----
    from src.physics.turbulence import TurbulenceModel
    tm = TurbulenceModel(cn2_ground=1.7e-14, wind_rms_speed=21.0)
    sigma_px = tm.image_domain_sigma(distance_km=1.0)
    r0_cm    = tm.fried_parameter_cm(distance_km=1.0)
    scintillation = tm.scintillation_index(distance_km=1.0)
"""

from __future__ import annotations

import math


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
WAVELENGTH_M: float = 1550e-9       # Default FSO wavelength: 1550 nm (C-band)
_TWO_PI: float = 2.0 * math.pi


class TurbulenceModel:
    """
    Physics model for atmospheric optical turbulence driven by Cn².

    Parameters
    ----------
    cn2_ground : float
        Ground-level refractive-index structure parameter in m^(-2/3).
        Typical values:
          Weak turbulence  : Cn² ~ 1e-17  m^(-2/3)
          Moderate         : Cn² ~ 1e-14  m^(-2/3)
          Strong turbulence: Cn² ~ 1e-12  m^(-2/3)
        Default: 1.7e-14 (moderate, SIH benchmark default)
    wind_rms_speed : float
        RMS wind speed in m/s for Hufnagel-Valley profile.
        Default: 21.0 m/s (day-time moderate wind)
    wavelength_m : float
        Optical wavelength in metres. Default: 1550e-9 m (telecom C-band).
    """

    def __init__(
        self,
        cn2_ground: float = 1.7e-14,
        wind_rms_speed: float = 21.0,
        wavelength_m: float = WAVELENGTH_M,
    ):
        self.cn2_ground = max(cn2_ground, 1e-20)   # Guard against zero/negative
        self.wind_rms_speed = wind_rms_speed
        self.wavelength_m = wavelength_m

    # ------------------------------------------------------------------
    # 1. Rytov Variance (log-amplitude scintillation measure)
    # ------------------------------------------------------------------

    def rytov_variance(self, distance_km: float) -> float:
        """
        Rytov log-amplitude variance σ²_R for a plane wave through a
        homogeneous turbulent path.

        Formula (Andrews & Phillips, Eq. 5.14):
            σ²_R = 1.23 · Cn² · k^(7/6) · L^(11/6)

        Valid in the weak-turbulence regime (σ²_R ≲ 0.3).

        Parameters
        ----------
        distance_km : float
            Propagation distance in kilometres.

        Returns
        -------
        float
            Dimensionless Rytov variance.
        """
        L = max(distance_km, 1e-6) * 1000.0          # Convert km → m
        k = _TWO_PI / self.wavelength_m               # Optical wave-number (rad/m)
        return 1.23 * self.cn2_ground * (k ** (7.0 / 6.0)) * (L ** (11.0 / 6.0))

    # ------------------------------------------------------------------
    # 2. Fried Coherence Parameter r₀ (cm)
    # ------------------------------------------------------------------

    def fried_parameter_cm(self, distance_km: float) -> float:
        """
        Fried coherence length r₀ — the aperture diameter over which
        turbulence causes approximately one radian of wavefront phase error.

        Formula (Hardy, Eq. 2.31):
            r₀ = 0.185 · (λ² / (Cn² · L))^(3/5)

        A larger r₀ means less severe turbulence.
        Typical values: r₀ = 1–30 cm for near-ground FSO links.

        Parameters
        ----------
        distance_km : float
            Propagation distance in kilometres.

        Returns
        -------
        float
            Fried parameter in **centimetres**.
        """
        L = max(distance_km, 1e-6) * 1000.0
        # Protect against degenerate Cn²·L product
        cn2_L = self.cn2_ground * L
        if cn2_L <= 0:
            return float('inf')
        r0_m = 0.185 * ((self.wavelength_m ** 2) / cn2_L) ** (3.0 / 5.0)
        return r0_m * 100.0   # m → cm

    # ------------------------------------------------------------------
    # 3. Isoplanatic Angle θ₀ (μrad)
    # ------------------------------------------------------------------

    def isoplanatic_angle_urad(self, distance_km: float) -> float:
        """
        Isoplanatic angle θ₀ — angular extent over which the turbulence
        is essentially uniform (relevant for beacon tracking FOV design).

        θ₀ ≈ 0.314 · (r₀ / L)   [radians]

        Parameters
        ----------
        distance_km : float
            Propagation path length in kilometres.

        Returns
        -------
        float
            Isoplanatic angle in **microradians**.
        """
        L = max(distance_km, 1e-6) * 1000.0
        r0_m = self.fried_parameter_cm(distance_km) / 100.0
        theta_rad = 0.314 * r0_m / L
        return theta_rad * 1e6   # rad → μrad

    # ------------------------------------------------------------------
    # 4. Image-domain Gaussian noise σ (pixels)
    # ------------------------------------------------------------------

    def image_domain_sigma(
        self,
        distance_km: float = 1.0,
        pixels_per_deg: float = 160.0,
        max_sigma_px: float = 20.0,
    ) -> float:
        """
        Map the Rytov variance to an equivalent image-plane Gaussian noise
        standard deviation in pixels.

        The turbulence causes intensity scintillation (σ²_R) and wavefront
        tilt that blurs the beacon.  We model this as additive Gaussian
        noise whose standard deviation scales with √σ²_R, calibrated so
        that moderate turbulence (Cn² = 1.7e-14) at 1 km maps to ~15 px
        at the default 640×480 / 4°×3° camera (160 px/deg).

        Parameters
        ----------
        distance_km : float
            Propagation distance in km.
        pixels_per_deg : float
            Camera pixel density in px/deg (default 160 px/deg = 640px/4°).
        max_sigma_px : float
            Hard cap — matches the PS noise gate maximum of σ = 20 px.

        Returns
        -------
        float
            Gaussian noise σ in **pixels** (capped at max_sigma_px).
        """
        sigma_r2 = self.rytov_variance(distance_km)
        # Empirical calibration: Cn²=1.7e-14, L=1km, 160px/deg → ~15 px
        # Derivation: sigma_px = C * sqrt(sigma_r2) / px_per_deg
        #   15 = C * sqrt(0.338) / 160  → C ≈ 4125
        # Cross-check weak: Cn²=1e-17 → sigma_r2≈2e-4 → sigma_px≈0.36px (good)
        CALIBRATION = 4125.0
        sigma_px = CALIBRATION * math.sqrt(sigma_r2) / pixels_per_deg
        return min(sigma_px, max_sigma_px)

    # ------------------------------------------------------------------
    # 5. Scintillation Index (for completeness / link-budget display)
    # ------------------------------------------------------------------

    def scintillation_index(self, distance_km: float) -> float:
        """
        Scintillation index SI — normalised intensity variance.

        Weak turbulence approximation: SI ≈ σ²_R (Rytov variance).
        Returns values in [0, 1+].  SI > 1 indicates saturated scintillation
        (strong turbulence, Rytov approximation breaks down above ~0.5).

        Parameters
        ----------
        distance_km : float
            Propagation distance in km.

        Returns
        -------
        float
            Dimensionless scintillation index.
        """
        return min(self.rytov_variance(distance_km), 2.0)   # Cap at 2.0 for display

    # ------------------------------------------------------------------
    # 6. Hufnagel-Valley Cn² at altitude (for future multi-layer support)
    # ------------------------------------------------------------------

    def cn2_at_altitude_m(self, altitude_m: float) -> float:
        """
        Hufnagel-Valley 5/7 profile: Cn²(h).

        HV-5/7 formula (Andrews & Phillips, Eq. 12.4):
            Cn²(h) = 0.00594 · (v/27)² · (1e-5 · h)^10 · exp(-h/1000)
                   + 2.7e-16 · exp(-h/1500)
                   + A · exp(-h/100)

        where:
            v  = wind speed (m/s),
            h  = altitude (m),
            A  = Cn²_ground (m^-2/3) at h=0.

        Parameters
        ----------
        altitude_m : float
            Altitude above ground in metres.

        Returns
        -------
        float
            Cn² at the given altitude in m^(-2/3).
        """
        v = self.wind_rms_speed
        h = max(altitude_m, 0.0)
        term1 = 0.00594 * (v / 27.0) ** 2 * (1e-5 * h) ** 10 * math.exp(-h / 1000.0)
        term2 = 2.7e-16 * math.exp(-h / 1500.0)
        term3 = self.cn2_ground * math.exp(-h / 100.0)
        return term1 + term2 + term3

    # ------------------------------------------------------------------
    # 7. Convenience: summary dict for UI display
    # ------------------------------------------------------------------

    def compute_all(self, distance_km: float = 1.0) -> dict:
        """
        Compute all turbulence metrics for a given propagation distance.

        Returns a dict suitable for display in the UI:
            r0_cm, rytov_var, scintillation_idx,
            isoplanatic_angle_urad, image_sigma_px, regime_label
        """
        r0 = self.fried_parameter_cm(distance_km)
        rv = self.rytov_variance(distance_km)
        si = self.scintillation_index(distance_km)
        theta = self.isoplanatic_angle_urad(distance_km)
        sigma_px = self.image_domain_sigma(distance_km)

        if rv < 0.1:
            regime = "Weak"
        elif rv < 0.5:
            regime = "Moderate"
        elif rv < 1.0:
            regime = "Strong"
        else:
            regime = "Saturated"

        return {
            "r0_cm":                  round(r0, 3),
            "rytov_variance":         round(rv, 6),
            "scintillation_index":    round(si, 4),
            "isoplanatic_angle_urad": round(theta, 3),
            "image_sigma_px":         round(sigma_px, 2),
            "regime":                 regime,
        }
