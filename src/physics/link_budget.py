import math

class LinkBudgetModel:
    """
    Computes real-world FSOC link budget parameters mapping simulation
    tracking error (pointing error) to actual received power degradation.
    """
    def __init__(
        self,
        wavelength_nm: float = 1550,
        beam_divergence_mrad: float = 0.5,
        tx_power_dBm: float = 33.0,     # 2W Tx power
        tx_gain_dB: float = 105.0,      # Tx telescope gain
        rx_gain_dB: float = 105.0,      # Rx telescope gain
        rx_aperture_m: float = 0.2,     # 20cm receiver aperture
        atmospheric_transmittance: float = 0.7,
        rx_sensitivity_dBm: float = -38.0
    ):
        self.wavelength_m = wavelength_nm * 1e-9
        self.div_rad = beam_divergence_mrad * 1e-3
        self.P_tx = tx_power_dBm
        self.G_tx = tx_gain_dB
        self.G_rx = rx_gain_dB
        self.rx_aperture = rx_aperture_m
        self.tau_atm = atmospheric_transmittance
        self.rx_sensitivity = rx_sensitivity_dBm
        
    def compute(self, distance_km: float, pointing_error_px: float, fov_deg: float = 4.0, res_px: float = 640.0) -> dict:
        """
        Maps tracking error in pixels to Pointing Loss in dB and Received Power in dBm.
        """
        distance_m = distance_km * 1000.0
        
        # 1. Convert pixel error to angular pointing error (microradians)
        px_per_deg = res_px / fov_deg
        deg_error = pointing_error_px / px_per_deg
        rad_error = math.radians(deg_error)
        urad_error = rad_error * 1e6
        
        # 2. Geometric Loss (Free Space Path Loss approximation for beams)
        W_L = distance_m * self.div_rad # Beam radius at distance L
        if W_L > self.rx_aperture:
            # Fraction of power intercepted by Rx aperture
            geometric_loss_dB = 20 * math.log10(W_L / self.rx_aperture)
        else:
            geometric_loss_dB = 0.0
            
        # 3. Pointing Loss (Gaussian beam approximation)
        # Loss(dB) = 4.343 * 8 * (theta_error / theta_divergence)^2
        pointing_loss_dB = 4.343 * 8.0 * (rad_error / self.div_rad)**2
        
        # 4. Atmospheric Loss
        atm_loss_dB = -10 * math.log10(self.tau_atm)
        
        # 5. Received Power & Margin
        P_rx = self.P_tx + self.G_tx + self.G_rx - geometric_loss_dB - atm_loss_dB - pointing_loss_dB
        margin = P_rx - self.rx_sensitivity
        
        return {
            "pointing_error_urad": urad_error,
            "geometric_loss_dB": geometric_loss_dB,
            "pointing_loss_dB": pointing_loss_dB,
            "received_power_dBm": P_rx,
            "margin_dB": margin,
            "link_status": "UP" if margin > 0 else "DOWN"
        }
