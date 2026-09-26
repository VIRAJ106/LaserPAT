import math
import numpy as np

# Typical attenuation coefficients (gamma in dB/km)
# Reference: Domain Research Section 6.5
WEATHER_ATTENUATION_DB_KM = {
    "clear": 0.2,
    "haze": 3.0,
    "light_fog": 15.0,
    "fog": 50.0,
    "dense_fog": 150.0,
    "rain": 6.0,
    "low_light": 0.2  # Low light doesn't necessarily attenuate more, just lower ambient
}

def get_gamma_for_weather(preset: str) -> float:
    return WEATHER_ATTENUATION_DB_KM.get(preset.lower(), 0.2)

def compute_transmittance(gamma_db_km: float, distance_km: float) -> float:
    """
    Computes atmospheric transmittance (0 to 1) using Beer-Lambert law.
    tau_atm = exp(-gamma * L) where gamma is the extinction coefficient.
    Since gamma is given in dB/km, we convert it.
    Attenuation in dB = 10 * log10(1 / tau)
    tau = 10^(-attenuation_dB / 10)
    """
    attenuation_db = gamma_db_km * distance_km
    tau = 10 ** (-attenuation_db / 10.0)
    return tau

def apply_weather_degradation(image: np.ndarray, weather_preset: str, distance_km: float = 1.0) -> np.ndarray:
    """
    Degrades image contrast and brightness based on atmospheric attenuation.
    """
    gamma = get_gamma_for_weather(weather_preset)
    tau = compute_transmittance(gamma, distance_km)
    
    # Scale intensities by transmittance (signal loss)
    # Simple model: target intensity drops, background scattering (path radiance) increases
    # For now, just a linear scaling of the signal + a base ambient level.
    ambient = 20 if weather_preset not in ["clear", "low_light"] else 0
    
    degraded = image.astype(np.float32) * tau + ambient
    return np.clip(degraded, 0, 255).astype(np.uint8)
