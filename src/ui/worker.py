import time
import numpy as np
from PySide6.QtCore import QThread, Signal
from src.config import LaserConfig
from src.environment.world import World
from src.environment.motion import StraightMotion
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
from src.control.search_patterns import SpiralSearch

class SimulationWorker(QThread):
    # Signals to update GUI
    frame_ready = Signal(np.ndarray)
    stats_updated = Signal(dict)
    
    def __init__(self, config: LaserConfig):
        super().__init__()
        self.cfg = config
        self.running = False
        self.paused = False
        
        # Will initialize physics objects here
        self.world = None
        
    def setup_sim(self):
        self.world = World(*self.cfg.environment.world_size)
        
        bx, by = self.cfg.environment.world_size[0]/2, self.cfg.environment.world_size[1]/2
        bmotion = StraightMotion((bx, by), speed=2.0)
        self.beacon = Beacon(self.cfg.beacon.shape, self.cfg.beacon.size_px, bmotion)
        
        pmotion = StraightMotion((bx, by), speed=0.0) 
        self.platform = Platform(pmotion, jitter_max_px=self.cfg.disturbances.max_displacement_px)
        
        self.viewport = Viewport(*self.cfg.camera.resolution)
        self.gimbal = Gimbal(start_x=bx, start_y=by, max_rate_deg_s=self.cfg.camera.gimbal.max_pan_rate_deg_s)
        self.sensor = Sensor(self.viewport, self.gimbal)
        
        self.ai_verifier = AIVerifier("models/patch_verifier_cnn.onnx")
        self.kf = KalmanFilterCV()
        self.sm = StateMachine(lock_threshold_px=self.cfg.estimation.lock_threshold_px, 
                               required_lock_frames=self.cfg.estimation.lock_frames)
        
        self.pid_x = PIDController(self.cfg.control.kp, self.cfg.control.ki, self.cfg.control.kd, self.gimbal.max_v_px_frame)
        self.pid_y = PIDController(self.cfg.control.kp, self.cfg.control.ki, self.cfg.control.kd, self.gimbal.max_v_px_frame)
        
        self.search = SpiralSearch(bx, by, fov_size=self.cfg.camera.resolution[1])
        
    def run(self):
        self.running = True
        self.setup_sim()
        self.sm.start_search()
        
        dt = 1.0 / 30.0 # Target 30 FPS logic
        
        while self.running:
            if self.paused:
                time.sleep(0.1)
                continue
                
            loop_start = time.perf_counter()
            
            # Step Env
            self.beacon.step(dt)
            self.platform.step(dt)
            
            # Capture
            raw_frame = self.sensor.capture_frame(self.beacon)
            
            # Degrade
            degraded = apply_weather_degradation(raw_frame, self.cfg.disturbances.weather_preset)
            noisy = apply_sensor_noise(
                degraded, 
                self.cfg.disturbances.gaussian_sigma, 
                self.cfg.disturbances.poisson, 
                self.cfg.disturbances.salt_and_pepper_percent
            )
            
            # Detect
            candidates = extract_candidates(noisy)
            valid_det = False
            err = float('inf')
            dw_x, dw_y = 0.0, 0.0
            
            if len(candidates) > 0:
                centroids = []
                for cand in candidates:
                    cx, cy = calculate_centroid(noisy, cand)
                    centroids.append((cx, cy))
                    
                scores = self.ai_verifier.extract_and_verify(noisy, centroids)
                
                best_score = 0
                best_idx = -1
                for i, score in enumerate(scores):
                    if score > 0.5 and score > best_score:
                        best_score = score
                        best_idx = i
                
                if best_idx != -1:
                    cx, cy = centroids[best_idx]
                    cam_x, cam_y = self.gimbal.get_position()
                    left, _, top, _ = self.viewport.get_bounds(cam_x, cam_y)
                    dw_x, dw_y = left + cx, top + cy
                    valid_det = True
                    import math
                    err = math.hypot(dw_x - self.beacon.x, dw_y - self.beacon.y)
                    
            self.kf.predict()
            if valid_det:
                valid_det = self.kf.update(dw_x, dw_y)
                
            state = self.sm.update(valid_det, err)
                
            # Control
            if state == TrackingState.SEARCH:
                sx, sy = self.search.step(dt)
                self.gimbal.command_position(sx, sy)
            elif state in [TrackingState.ACQUIRE, TrackingState.LOCKED, TrackingState.COAST]:
                self.search.reset(*self.gimbal.get_position())
                px, py = self.kf.get_position()
                gx, gy = self.gimbal.get_position()
                vx = self.pid_x.compute(px - gx)
                vy = self.pid_y.compute(py - gy)
                self.gimbal.command_velocity(vx, vy)
                
            # Output
            # Draw crosshair or bounding box for display
            display_frame = noisy.copy()
            
            # Emit
            self.frame_ready.emit(display_frame)
            stats = {
                "state": state.name,
                "error": err,
                "gimbal_x": self.gimbal.x,
                "gimbal_y": self.gimbal.y,
                "target_x": self.beacon.x,
                "target_y": self.beacon.y
            }
            self.stats_updated.emit(stats)
            
            loop_end = time.perf_counter()
            elapsed = loop_end - loop_start
            sleep_time = dt - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
                
    def stop(self):
        self.running = False
        self.wait()
