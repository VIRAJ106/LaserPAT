import math

# All pixel↔degree↔µrad↔world conversions live here
PX_PER_DEG = 640 / 4.0   # 160 px/deg (from default FOV)
DEG_PER_PX = 1.0 / PX_PER_DEG
URAD_PER_PX = math.radians(DEG_PER_PX) * 1e6  # ≈ 109 µrad/px

def px_to_urad(px: float, px_per_deg: float = PX_PER_DEG) -> float:
    deg = px / px_per_deg
    return math.radians(deg) * 1e6

def urad_to_px(urad: float, px_per_deg: float = PX_PER_DEG) -> float:
    deg = math.degrees(urad / 1e6)
    return deg * px_per_deg

def px_to_deg(px: float, px_per_deg: float = PX_PER_DEG) -> float:
    return px / px_per_deg

def deg_to_px(deg: float, px_per_deg: float = PX_PER_DEG) -> float:
    return deg * px_per_deg
