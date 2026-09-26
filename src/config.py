import yaml
import os
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional

@dataclass
class EnvironmentConfig:
    world_size: Tuple[int, int] = (2000, 2000)
    platform_motion_type: str = "linear"
    max_speed_px_frame: int = 20

@dataclass
class DistractorConfig:
    """Config for a single distractor beacon (non-tracked light source)."""
    shape: str = "square"
    size_px: Tuple[int, int] = (16, 16)  # Deliberately different from target
    motion: str = "straight"
    initial_location: str = "random"


@dataclass
class BeaconConfig:
    shape: str = "square"
    size_px: Tuple[int, int] = (10, 10)
    motion: str = "straight"
    initial_location: str = "random"
    # ── Multi-beacon / size-discrimination ──
    # distractors: 0–2 additional light sources rendered in the same frame.
    # The tracker will discriminate by comparing each candidate’s bounding
    # box to `target_size_px` (default = same as primary beacon).
    num_distractors: int = 0          # 0–2 extra beacons (1–3 total light sources)
    distractors: List["DistractorConfig"] = field(default_factory=list)
    # Size-discriminator target reference.  Set to (-1,-1) to auto-match primary size.
    target_size_px: Tuple[int, int] = (-1, -1)
    size_tolerance: float = 0.5       # Accept blobs within ±50% of target_size_px

@dataclass
class GimbalConfig:
    max_pan_rate_deg_s: float = 5.0
    max_tilt_rate_deg_s: float = 5.0

@dataclass
class CameraConfig:
    initial_position: str = "center"
    resolution: Tuple[int, int] = (640, 480)
    fov_deg: Tuple[float, float] = (4.0, 3.0)
    monochrome: bool = True
    gimbal: GimbalConfig = field(default_factory=GimbalConfig)

@dataclass
class DisturbancesConfig:
    gaussian_sigma: float = 20.0
    poisson: bool = True
    salt_and_pepper_percent: float = 10.0
    max_displacement_px: float = 20.0
    weather_preset: str = "fog"
    derive_from_cn2: bool = True
    cn2_ground: float = 1.7e-14
    wind_rms_speed: float = 21.0

@dataclass
class DetectionConfig:
    acquisition_mode: str = "blind_spiral"
    use_cnn_verifier: bool = True

@dataclass
class EstimationConfig:
    filter_type: str = "kf_cv"
    lock_threshold_px: float = 10.0
    lock_frames: int = 3

@dataclass
class LinkBudgetConfig:
    wavelength_nm: float = 1550.0
    beam_divergence_mrad: float = 0.5
    report_at_end_of_run: bool = True

@dataclass
class ControlConfig:
    controller_type: str = "pid"
    kp: float = 0.5
    ki: float = 0.05
    kd: float = 0.1
    antiwindup: bool = True

@dataclass
class AppConfig:
    scenario_name: str = "Default"
    duration_seconds: float = 60.0
    seed: int = 42
    environment: EnvironmentConfig = field(default_factory=EnvironmentConfig)
    beacon: BeaconConfig = field(default_factory=BeaconConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    disturbances: DisturbancesConfig = field(default_factory=DisturbancesConfig)
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    estimation: EstimationConfig = field(default_factory=EstimationConfig)
    control: ControlConfig = field(default_factory=ControlConfig)
    link_budget: LinkBudgetConfig = field(default_factory=LinkBudgetConfig)

def load_config(path: str) -> AppConfig:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")
    
    with open(path, 'r') as f:
        data = yaml.safe_load(f)
        
    cfg = AppConfig(
        scenario_name=data.get('scenario', {}).get('name', 'Default'),
        duration_seconds=data.get('scenario', {}).get('duration_seconds', 60),
        seed=data.get('scenario', {}).get('seed', 42)
    )
    
    if 'environment' in data:
        cfg.environment.world_size = tuple(data['environment'].get('world_size', (2000, 2000)))
        pm = data['environment'].get('platform_motion', {})
        cfg.environment.platform_motion_type = pm.get('type', 'linear')
        cfg.environment.max_speed_px_frame = pm.get('max_speed_px_frame', 20)
        
    if 'beacon' in data:
        cfg.beacon.shape = data['beacon'].get('shape', 'square')
        cfg.beacon.size_px = tuple(data['beacon'].get('size_px', (10, 10)))
        cfg.beacon.motion = data['beacon'].get('motion', 'straight')
        cfg.beacon.initial_location = data['beacon'].get('initial_location', 'random')
        target_sz = data['beacon'].get('target_size_px', [-1, -1])
        cfg.beacon.target_size_px = tuple(target_sz)
        cfg.beacon.size_tolerance = float(data['beacon'].get('size_tolerance', 0.5))
        # Parse optional distractor list
        cfg.beacon.distractors = []
        for d in data['beacon'].get('distractors', [])[:2]:  # Cap at 2 distractors
            dc = DistractorConfig(
                shape=d.get('shape', 'square'),
                size_px=tuple(d.get('size_px', [16, 16])),
                motion=d.get('motion', 'straight'),
                initial_location=d.get('initial_location', 'random'),
            )
            cfg.beacon.distractors.append(dc)
        cfg.beacon.num_distractors = len(cfg.beacon.distractors)
        
    if 'camera' in data:
        cfg.camera.initial_position = data['camera'].get('initial_position', 'center')
        cfg.camera.resolution = tuple(data['camera'].get('resolution', (640, 480)))
        cfg.camera.fov_deg = tuple(data['camera'].get('fov_deg', (4.0, 3.0)))
        cfg.camera.monochrome = data['camera'].get('monochrome', True)
        if 'gimbal' in data['camera']:
            cfg.camera.gimbal.max_pan_rate_deg_s = data['camera']['gimbal'].get('max_pan_rate_deg_s', 5.0)
            cfg.camera.gimbal.max_tilt_rate_deg_s = data['camera']['gimbal'].get('max_tilt_rate_deg_s', 5.0)
            
    if 'disturbances' in data:
        sn = data['disturbances'].get('sensor_noise', {})
        cfg.disturbances.gaussian_sigma = sn.get('gaussian_sigma', 20.0)
        cfg.disturbances.poisson = sn.get('poisson', True)
        cfg.disturbances.salt_and_pepper_percent = sn.get('salt_and_pepper_percent', 10.0)
        
        cfg.disturbances.max_displacement_px = data['disturbances'].get('jitter', {}).get('max_displacement_px', 20.0)
        cfg.disturbances.weather_preset = data['disturbances'].get('weather_preset', 'fog')
        
        wp = data['disturbances'].get('weather_physics', {})
        cfg.disturbances.derive_from_cn2 = wp.get('derive_from_cn2', True)
        cfg.disturbances.cn2_ground = wp.get('cn2_ground', 1.7e-14)
        cfg.disturbances.wind_rms_speed = wp.get('wind_rms_speed', 21.0)
        
    if 'detection' in data:
        cfg.detection.acquisition_mode = data['detection'].get('acquisition_mode', 'blind_spiral')
        cfg.detection.use_cnn_verifier = data['detection'].get('use_cnn_verifier', True)
        
    if 'estimation' in data:
        cfg.estimation.filter_type = data['estimation'].get('filter', 'kf_cv')
        cfg.estimation.lock_threshold_px = data['estimation'].get('lock_threshold_px', 25.0)
        cfg.estimation.lock_frames = data['estimation'].get('lock_frames', 3)
        
    if 'control' in data:
        cfg.control.controller_type = data['control'].get('controller', 'pid')
        pid = data['control'].get('pid', {})
        cfg.control.kp = pid.get('kp', 0.4)
        cfg.control.ki = pid.get('ki', 0.01)
        cfg.control.kd = pid.get('kd', 0.02)
        cfg.control.antiwindup = pid.get('antiwindup', True)

    if 'link_budget' in data:
        cfg.link_budget.wavelength_nm = data['link_budget'].get('wavelength_nm', 1550.0)
        cfg.link_budget.beam_divergence_mrad = data['link_budget'].get('beam_divergence_mrad', 0.5)
        cfg.link_budget.report_at_end_of_run = data['link_budget'].get('report_at_end_of_run', True)

    # ------------------------------------------------------------------
    # Cn² → Gaussian noise derivation
    # When derive_from_cn2 is True, override gaussian_sigma with a
    # physically grounded value from the Rytov variance (Andrews & Phillips).
    # The TurbulenceModel is also stored on cfg for UI display of r₀, SI, etc.
    # ------------------------------------------------------------------
    from src.physics.turbulence import TurbulenceModel  # late import avoids circular dep
    cfg.turbulence = TurbulenceModel(
        cn2_ground=cfg.disturbances.cn2_ground,
        wind_rms_speed=cfg.disturbances.wind_rms_speed,
        wavelength_m=1550e-9,
    )
    if cfg.disturbances.derive_from_cn2:
        # Compute σ at the nominal 1 km link distance used in apply_weather_degradation
        derived_sigma = cfg.turbulence.image_domain_sigma(
            distance_km=1.0,
            pixels_per_deg=cfg.camera.resolution[0] / cfg.camera.fov_deg[0],
            max_sigma_px=20.0,
        )
        cfg.disturbances.gaussian_sigma = derived_sigma

    from src.physics.link_budget import LinkBudgetModel
    cfg.link_budget_model = LinkBudgetModel(
        wavelength_nm=cfg.link_budget.wavelength_nm,
        beam_divergence_mrad=cfg.link_budget.beam_divergence_mrad
    )

    return cfg

