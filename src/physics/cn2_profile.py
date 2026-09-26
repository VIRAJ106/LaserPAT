import math

def hufnagel_valley_cn2(altitude_m: float, ground_cn2: float = 1.7e-14, v_rms: float = 21.0) -> float:
    """
    Computes the refractive index structure parameter C_n^2 at a given altitude
    using the Hufnagel-Valley 5/7 model.
    Reference: Domain Research Section 6.2
    
    Args:
        altitude_m: Altitude in meters.
        ground_cn2: Ground level C_n^2 (typically 1.7e-14).
        v_rms: RMS wind speed in m/s (typically 21 m/s).
        
    Returns:
        C_n^2 value (m^-2/3).
    """
    h = altitude_m
    if h < 0:
        h = 0.0
        
    term1 = 0.00594 * ((v_rms / 27.0) ** 2) * ((1e-5 * h) ** 10) * math.exp(-h / 1000.0)
    term2 = 2.7e-16 * math.exp(-h / 1500.0)
    term3 = ground_cn2 * math.exp(-h / 100.0)
    
    return term1 + term2 + term3
