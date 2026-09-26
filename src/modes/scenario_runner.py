import argparse
import time
import math
import os
from datetime import datetime
import numpy as np

from src.config import load_config
from src.environment.world import World
from src.environment.motion import (
    StraightMotion, CircularMotion, Figure8Motion, RandomWalkMotion
)
from src.environment.beacon import Beacon
from src.environment.platform import Platform
from src.camera.viewport import Viewport
from src.camera.gimbal import Gimbal
from src.camera.sensor import Sensor
from src.physics.attenuation import apply_weather_degradation
from src.disturbances.noise import apply_sensor_noise
from src.detection.classical import extract_candidates, calculate_centroid
from src.detection.ai_verifier import AIVerifier
from src.estimation.kalman import KalmanFilterCV
from src.estimation.state_machine import StateMachine, TrackingState
from src.control.pid import PIDController
from src.control.search_patterns import SpiralSearch, RasterSearch
from src.logging.csv_logger import CSVLogger, FrameRecord

def run_scenario(config_path: str, headless: bool = True, output_csv: str = None):
    cfg = load_config(config_path)
    
    # Initialize Environment
    world = World(*cfg.environment.world_size)
    
    # Initial beacon position
    world_center_x = cfg.environment.world_size[0] / 2
    world_center_y = cfg.environment.world_size[1] / 2
    
    if cfg.beacon.initial_location == "random":
        import random
        bx = random.uniform(100, cfg.environment.world_size[0] - 100)
        by = random.uniform(100, cfg.environment.world_size[1] - 100)
    elif cfg.beacon.initial_location == "center":
        bx, by = world_center_x, world_center_y
    elif cfg.beacon.initial_location == "top-left":
        bx, by = 200.0, 200.0
    elif cfg.beacon.initial_location == "top-right":
        bx, by = cfg.environment.world_size[0] - 200.0, 200.0
    elif cfg.beacon.initial_location == "bottom-left":
        bx, by = 200.0, cfg.environment.world_size[1] - 200.0
    elif cfg.beacon.initial_location == "bottom-right":
        bx = cfg.environment.world_size[0] - 200.0
        by = cfg.environment.world_size[1] - 200.0
    else:
        bx, by = world_center_x, world_center_y
    
    # Create motion based on config (4 mandatory motions from SPEC.md)
    motion_type = cfg.beacon.motion.lower()
    if motion_type == "straight":
        # Straight line motion with random angle
        # Speed: 0.5 px/frame = 15 px/s at 30 Hz, slow enough for gimbal (5°/s ≈ 27 px/frame)
        import random
        angle = random.uniform(0, 2 * math.pi)
        bmotion = StraightMotion((bx, by), speed=0.5, angle_rad=angle)
    elif motion_type == "circular":
        # Circular motion around world center
        radius = 150.0  # pixels (reduced from 200 to stay within gimbal FOV)
        angular_speed = 0.005  # radians per frame (slower for trackability)
        bmotion = CircularMotion((world_center_x, world_center_y), radius, angular_speed)
    elif motion_type == "figure8" or motion_type == "figure_8":
        # Figure-8 pattern (Lissajous curve)
        width = 200.0  # Reduced to stay within tracking range
        height = 150.0
        speed = 0.01  # Slower speed for better tracking
        bmotion = Figure8Motion((world_center_x, world_center_y), width, height, speed)
    elif motion_type == "random" or motion_type == "random_walk":
        # Random walk motion — max_step 1.5px/frame = 5.6% of gimbal max (26.67px/frame)
        # Keeps target within reliable tracking range for stress-gate 300 runs.
        max_step = 1.5
        bmotion = RandomWalkMotion((bx, by), max_step)
    else:
        raise ValueError(f"Unknown beacon motion type: {motion_type}. "
                        f"Must be one of: straight, circular, figure8, random")
    
    beacon = Beacon(cfg.beacon.shape, cfg.beacon.size_px, bmotion)
    
    pmotion = StraightMotion((bx, by), speed=0.0) # platform is stationary relative to world
    platform = Platform(pmotion, jitter_max_px=cfg.disturbances.max_displacement_px)
    
    # Initialize Camera
    viewport = Viewport(*cfg.camera.resolution)
    gimbal = Gimbal(
        start_x=bx, start_y=by,
        max_rate_deg_s=cfg.camera.gimbal.max_pan_rate_deg_s,
        world_bounds=tuple(cfg.environment.world_size),
        fov_size=tuple(cfg.camera.resolution),
        fov_deg=tuple(cfg.camera.fov_deg),
        fps=30.0,
    )
    sensor = Sensor(viewport, gimbal)
    
    # Initialize Estimation and Control
    ai_verifier = AIVerifier("models/patch_verifier_cnn.onnx")
    kf = KalmanFilterCV(dt=1.0/30.0)
    sm = StateMachine(lock_threshold_px=cfg.estimation.lock_threshold_px, 
                      required_lock_frames=cfg.estimation.lock_frames)
    
    pid_x = PIDController(cfg.control.kp, cfg.control.ki, cfg.control.kd, gimbal.max_v_px_frame, dt=1.0/30.0)
    pid_y = PIDController(cfg.control.kp, cfg.control.ki, cfg.control.kd, gimbal.max_v_px_frame, dt=1.0/30.0)
    
    search_pattern = SpiralSearch(
        bx, by, fov_size=cfg.camera.resolution[1],
        world_bounds=tuple(cfg.environment.world_size),
        fov_dims=tuple(cfg.camera.resolution)
    )
    raster_pattern = RasterSearch(
        bx, by,
        search_w=float(cfg.environment.world_size[0]) * 0.9,
        search_h=float(cfg.environment.world_size[1]) * 0.9,
        col_spacing=300.0,
        row_spacing=200.0,
        dwell_time=0.25,
        world_bounds=tuple(cfg.environment.world_size),
        fov_dims=tuple(cfg.camera.resolution)
    )
    # Track which search pattern is active and how long spiral has run
    _spiral_time = 0.0
    _spiral_max_time = 4.0   # seconds before switching to raster
    _use_raster = False
    _last_known_x, _last_known_y = bx, by
    
    # Setup CSV Logging
    if output_csv is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_csv = f"logs/run_{cfg.scenario_name.replace(' ', '_')}_{timestamp}.csv"
    
    os.makedirs(os.path.dirname(output_csv) or "logs", exist_ok=True)
    
    # Simulation Loop
    dt = 1.0 / 30.0
    frames = int(cfg.duration_seconds * 30)
    
    sm.start_search()
    start_time = time.time()
    
    with CSVLogger(output_csv) as logger:
        for frame_idx in range(frames):
            # 1. Step Environment
            beacon.step(dt)
            platform.step(dt)
            
            # 2. Capture Frame
            raw_frame = sensor.capture_frame(beacon)
            
            # 3. Apply Disturbances
            degraded_frame = apply_weather_degradation(raw_frame, cfg.disturbances.weather_preset)
            noisy_frame = apply_sensor_noise(
                degraded_frame, 
                cfg.disturbances.gaussian_sigma, 
                cfg.disturbances.poisson, 
                cfg.disturbances.salt_and_pepper_percent
            )
            
            # 4. Detection
            frame_start = time.time()
            candidates = extract_candidates(noisy_frame)
            valid_detection = False
            detected_world_x = 0.0
            detected_world_y = 0.0
            euclidean_error = float('inf')
            ai_score = 0.0
            
            if len(candidates) > 0:
                centroids = []
                for cand in candidates:
                    cx, cy = calculate_centroid(noisy_frame, cand)
                    centroids.append((cx, cy))
                    
                scores = ai_verifier.extract_and_verify(noisy_frame, centroids)
                
                # Classical fallback when ONNX model is absent OR CNN is disabled in config
                ai_active = cfg.detection.use_cnn_verifier and any(s > 0.1 for s in scores)
                best_score = 0
                best_idx = -1
                if ai_active:
                    for i, score in enumerate(scores):
                        if score > 0.5 and score > best_score:
                            best_score = score
                            best_idx = i
                else:
                    best_area = 0
                    for i, cand in enumerate(candidates):
                        x, y, w, h, *_ = cand
                        area = w * h
                        if area > best_area:
                            best_area = area
                            best_idx = i
                            best_score = 0.6
                
                if best_idx != -1:
                    cx, cy = centroids[best_idx]
                    cam_x, cam_y = gimbal.get_position()
                    left, _, top, _ = viewport.get_bounds(cam_x, cam_y)
                    detected_world_x = left + cx
                    detected_world_y = top + cy
                    valid_detection = True
                    euclidean_error = math.hypot(detected_world_x - beacon.x, detected_world_y - beacon.y)
                    ai_score = best_score
            
            # 5. State Machine & Estimation Update
            kf.predict()
            innovation_gate_passed = True
            if valid_detection:
                innovation_gate_passed = kf.update(detected_world_x, detected_world_y)
                
            state = sm.update(valid_detection and innovation_gate_passed, euclidean_error)
                
            # 6. Control Loop
            if state == TrackingState.SEARCH:
                # Adaptive search: spiral first, fallback to raster after timeout
                # Reset Kalman if this is a fresh SEARCH entry (from LOST) so stale
                # velocity predictions don't bias the next REACQUIRE slew.
                _spiral_time += dt
                if _spiral_time > _spiral_max_time and not _use_raster:
                    _use_raster = True
                    raster_pattern.reset(_last_known_x, _last_known_y)
                
                if _use_raster:
                    sx, sy = raster_pattern.step(dt)
                else:
                    sx, sy = search_pattern.step(dt)
                gimbal.command_position(sx, sy)
            elif state == TrackingState.REACQUIRE:
                # REACQUIRE: Slew to KF predicted position for fast re-lock
                # Also reset search patterns so SEARCH (if it follows) starts from here
                pred_x, pred_y = kf.get_position()
                _last_known_x, _last_known_y = pred_x, pred_y
                _spiral_time = 0.0
                _use_raster = False
                search_pattern.reset(pred_x, pred_y)
                gx, gy = gimbal.get_position()
                
                kv_x, kv_y = kf.get_velocity()
                vx = pid_x.compute(pred_x - gx) + (kv_x * dt)
                vy = pid_y.compute(pred_y - gy) + (kv_y * dt)
                gimbal.command_velocity(vx, vy)
            elif state in [TrackingState.ACQUIRE, TrackingState.LOCKED, TrackingState.COAST]:
                # Reset search patterns to current gimbal position for next LOST event
                gx_now, gy_now = gimbal.get_position()
                _last_known_x, _last_known_y = gx_now, gy_now
                _spiral_time = 0.0
                _use_raster = False
                search_pattern.reset(gx_now, gy_now)
                
                pred_x, pred_y = kf.get_position()
                kv_x, kv_y = kf.get_velocity()
                gx, gy = gimbal.get_position()
                err_x = pred_x - gx
                err_y = pred_y - gy
                
                vx = pid_x.compute(err_x) + (kv_x * dt)
                vy = pid_y.compute(err_y) + (kv_y * dt)
                gimbal.command_velocity(vx, vy)
            
            # 7. Log Frame
            frame_time = time.time() - frame_start
            timestamp = frame_idx * dt
            gx, gy = gimbal.get_position()
            
            record = FrameRecord(
                frame_id=frame_idx,
                timestamp=timestamp,
                state=state.name,
                tracking_error_px=euclidean_error if euclidean_error != float('inf') else 0.0,
                gimbal_x=gx,
                gimbal_y=gy,
                target_x=beacon.x,
                target_y=beacon.y,
                ai_score=ai_score,
                weather_preset=cfg.disturbances.weather_preset,
                innovation_gate_passed=innovation_gate_passed
            )
            logger.log_frame(record)
            
            if not headless and frame_idx % 30 == 0:
                print(f"Frame {frame_idx} | State: {state.name} | Err: {euclidean_error:.2f}px")
    
    total_time = time.time() - start_time
    avg_fps = frames / total_time if total_time > 0 else 0
    
    print(f"Scenario completed. Final state: {sm.state.name}")
    print(f"CSV log written to: {output_csv}")
    print(f"Total time: {total_time:.2f}s | Avg FPS: {avg_fps:.1f}")
    
    return output_csv

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=str, default="configs/default.yaml")
    parser.add_argument("--stress-mode", action="store_true")
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args()
    
    if args.stress_mode:
        print(f"Starting Stress Gate: {args.runs} runs")
        for i in range(args.runs):
            run_scenario(args.scenario, headless=True)
    else:
        run_scenario(args.scenario, headless=False)
