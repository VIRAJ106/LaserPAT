import time
import math
import numpy as np
import cv2
from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker
from src.config import AppConfig
from src.environment.world import World
from src.environment.motion import StraightMotion, CircularMotion, Figure8Motion, RandomWalkMotion
from src.environment.beacon import Beacon
from src.environment.platform import Platform
from src.camera.viewport import Viewport
from src.camera.gimbal import Gimbal
from src.camera.sensor import Sensor
from src.physics.attenuation import apply_weather_degradation
from src.disturbances.noise import apply_sensor_noise
from src.disturbances.jitter import apply_jitter
from src.detection.classical import extract_candidates, calculate_centroid, size_discriminate
from src.detection.ai_verifier import AIVerifier
from src.estimation.kalman import KalmanFilterCV
from src.estimation.state_machine import StateMachine, TrackingState
from src.control.pid import PIDController
from src.control.search_patterns import SpiralSearch, RasterSearch

class SimWorker(QThread):
    raw_frame_ready = Signal(np.ndarray, dict)
    world_state_ready = Signal(dict)  # NEW: Full world state for world view widget
    
    def __init__(self, config: AppConfig):
        super().__init__()
        self.cfg = config
        self.running = False
        self.paused = False
        self.cmd_mutex = QMutex()
        self.gimbal_v = (0.0, 0.0)
        self.gimbal_pos = (0.0, 0.0)
        self.mode = "VELOCITY"
        
    def setup_sim(self):
        """Initialize simulation with FULL world-scale motion."""
        world_w, world_h = self.cfg.environment.world_size
        self.world = World(world_w, world_h)
        
        # Beacon start position: respect config's initial_location setting.
        # "random" → beacon spawns anywhere in the world (forcing a real spiral scan).
        # This makes acquisition time measurements honest — the spiral search must
        # actually cover the field to find the beacon.
        # "center" → beacon starts at world center (beacon already in FOV, acq ~1 frame).
        import random as _beacon_rng
        margin = 100  # Keep beacon away from world edges to avoid instant clipping
        if getattr(self.cfg.beacon, 'initial_location', 'random') == 'random':
            bx = _beacon_rng.uniform(margin, world_w - margin)
            by = _beacon_rng.uniform(margin, world_h - margin)
        else:
            bx, by = world_w / 2, world_h / 2
        beacon_speed = 15.0  # Reasonable speed: 15 px/frame (camera max is 26.67)
        bmotion = StraightMotion((bx, by), speed=beacon_speed, angle_rad=0.785)  # 45 degrees
        
        # Physics: Derive beacon spot size from beam divergence if using Gaussian
        if self.cfg.beacon.shape == "gaussian" and hasattr(self.cfg, "link_budget"):
            import math
            div_rad = self.cfg.link_budget.beam_divergence_mrad / 1000.0
            div_deg = math.degrees(div_rad)
            px_per_deg = self.cfg.camera.resolution[0] / self.cfg.camera.fov_deg[0]
            # Spot diameter in pixels (4-sigma Gaussian coverage), minimum 10px to survive threshold
            diam_px = max(10, int(div_deg * px_per_deg * 4))
            beacon_size = (diam_px, diam_px)
            # CRITICAL: Keep cfg.beacon.size_px in sync so the size discriminator
            # reference (target_size_px auto-match) uses the ACTUAL rendered size.
            self.cfg.beacon.size_px = beacon_size
        else:
            beacon_size = self.cfg.beacon.size_px
            
        self.beacon = Beacon(self.cfg.beacon.shape, beacon_size, bmotion)
        
        # Platform starts static at center, then apply config
        pmotion = StraightMotion((bx, by), speed=0.0) 
        self.platform = Platform(pmotion, jitter_max_px=self.cfg.disturbances.max_displacement_px)
        self.set_platform_motion(self.cfg.environment.platform_motion_type.capitalize())
        
        self.viewport = Viewport(*self.cfg.camera.resolution)
        
        # Pass world bounds, FOV size, AND FOV deg — all three needed for
        # correct px_per_deg conversion and world-edge clamping.
        self.gimbal = Gimbal(
            start_x=bx,
            start_y=by,
            max_rate_deg_s=self.cfg.camera.gimbal.max_pan_rate_deg_s,
            world_bounds=(world_w, world_h),
            fov_size=tuple(self.cfg.camera.resolution),
            fov_deg=tuple(self.cfg.camera.fov_deg),
            fps=60.0,
        )
        
        self.sensor = Sensor(self.viewport, self.gimbal)

        # ── Distractor beacons (optional, 0–2 extra light sources) ──
        # Each distractor has its own size and motion, and is rendered into
        # the same frame as the primary beacon.  The size discriminator in
        # ProcessingWorker will filter them out by bounding-box size.
        self.distractor_beacons = []
        spawn_positions = [
            (world_w * 0.25, world_h * 0.25),  # Distractor 1: top-left quadrant
            (world_w * 0.75, world_h * 0.75),  # Distractor 2: bottom-right quadrant
        ]
        for idx, dcfg in enumerate(self.cfg.beacon.distractors[:2]):
            dx, dy = spawn_positions[idx]
            dmot = StraightMotion((dx, dy), speed=12.0,
                                  angle_rad=0.785 + idx * 1.5708)  # Different angle each
            db = Beacon(dcfg.shape, dcfg.size_px, dmot)
            self.distractor_beacons.append(db)
        
    def command_velocity(self, vx, vy):
        with QMutexLocker(self.cmd_mutex):
            self.mode = "VELOCITY"
            self.gimbal_v = (vx, vy)
            
    def command_position(self, px, py, snap=False):
        with QMutexLocker(self.cmd_mutex):
            self.mode = "POSITION"
            self.gimbal_pos = (px, py)
            self.gimbal_snap = snap
            
    def set_beacon_motion(self, motion_type: str):
        """Set beacon motion pattern with trackable speeds."""
        bx, by = self.beacon.x, self.beacon.y
        world_w, world_h = self.cfg.environment.world_size
        
        # Camera can move at most 26.67 px/frame (5 deg/s)
        # Beacon should be slower for reliable tracking
        
        if motion_type == "Straight":
            self.beacon.motion = StraightMotion((bx, by), speed=15.0, angle_rad=0.785)  # Moderate speed
        elif motion_type == "Circular":
            # Medium radius, slow angular speed
            radius = world_w / 5.0  # 400 px radius
            center = (world_w/2, world_h/2)
            self.beacon.motion = CircularMotion(center, radius=radius, angular_speed=0.015)
        elif motion_type == "Figure8":
            center = (world_w/2, world_h/2)
            self.beacon.motion = Figure8Motion(center, width=world_w*0.5, height=world_h*0.3, speed=0.015)
        elif motion_type == "Random":
            # max_step=6px/frame ≈ 22% of gimbal max (26.67px/frame).
            # Previously 10px/frame caused 87% target loss as the PID
            # derivative kick on sudden direction changes exceeded the
            # gimbal slew rate budget.
            self.beacon.motion = RandomWalkMotion((bx, by), max_step=6.0)

    def set_platform_motion(self, motion_type: str):
        """Set platform motion pattern. Uses FULL 2000×2000 world space."""
        px, py = self.platform.motion.x, self.platform.motion.y
        world_w, world_h = self.cfg.environment.world_size
        
        if motion_type == "Linear":
            # Use configured speed, fallback to default if not set or invalid
            speed = getattr(self.cfg.environment, 'max_speed_px_frame', world_w/200.0)
            if speed is None or speed == 0: speed = world_w/200.0
            self.platform.motion = StraightMotion((px, py), speed=speed)
        elif motion_type == "Circular":
            # Platform wobble with moderate radius
            self.platform.motion = CircularMotion((px, py), radius=world_w/20.0, angular_speed=0.01)
        elif motion_type == "Random":
            # Platform random walk
            speed = getattr(self.cfg.environment, 'max_speed_px_frame', world_w/200.0)
            if speed == 0: speed = world_w/200.0 # Make sure random walk actually walks if selected manually
            self.platform.motion = RandomWalkMotion((px, py), max_step=speed)
        else:
            self.platform.motion = StraightMotion((px, py), speed=0.0)  # Static

    def run(self):
        self.running = True
        self.setup_sim()
        dt = 1.0 / 60.0
        
        while self.running:
            if self.paused:
                time.sleep(0.1)
                continue
            loop_start = time.perf_counter()
            
            self.beacon.step(dt)
            # Step distractor beacons too
            for db in self.distractor_beacons:
                db.step(dt)
            self.platform.step(dt)
            
            with QMutexLocker(self.cmd_mutex):
                if self.mode == "VELOCITY":
                    self.gimbal.command_velocity(*self.gimbal_v)
                elif self.mode == "POSITION":
                    snap = getattr(self, 'gimbal_snap', False)
                    self.gimbal.command_position(*self.gimbal_pos, snap=snap)
                    self.gimbal_snap = False  # Reset after one snap
                    
            # Capture primary beacon, then render distractors on top
            raw_frame = self.sensor.capture_frame(self.beacon)
            for db in self.distractor_beacons:
                db.draw(raw_frame,
                        self.gimbal.x - self.viewport.width / 2,
                        self.gimbal.y - self.viewport.height / 2)
            
            gt = {
                "beacon_x": self.beacon.x,
                "beacon_y": self.beacon.y,
                "gimbal_x": self.gimbal.x,
                "gimbal_y": self.gimbal.y,
                "dt": dt
            }
            self.raw_frame_ready.emit(raw_frame, gt)
            
            # Emit world state for world view widget
            # Check if platform is actually moving
            platform_is_moving = False
            if hasattr(self.platform.motion, 'speed') and self.platform.motion.speed > 0.001:
                platform_is_moving = True
            elif hasattr(self.platform.motion, 'vx') and hasattr(self.platform.motion, 'vy'):
                if abs(self.platform.motion.vx) > 0.001 or abs(self.platform.motion.vy) > 0.001:
                    platform_is_moving = True
            
            world_state = {
                "beacon_x": self.beacon.x,
                "beacon_y": self.beacon.y,
                "gimbal_x": self.gimbal.x,
                "gimbal_y": self.gimbal.y,
                "platform_x": self.platform.motion.x if hasattr(self.platform.motion, 'x') else None,
                "platform_y": self.platform.motion.y if hasattr(self.platform.motion, 'y') else None,
                "platform_is_moving": platform_is_moving,
                "fov_px": (self.viewport.width, self.viewport.height),
                "world_size": (self.world.width, self.world.height),
                # Distractor positions for world-view rendering
                "distractors": [(db.x, db.y, db.w, db.h)
                                 for db in self.distractor_beacons],
                "tracking_state": getattr(self.proc_worker, 'current_state', 'IDLE') if hasattr(self, 'proc_worker') else "IDLE",
                "beacon_w": self.cfg.beacon.size_px[0],
                "beacon_h": self.cfg.beacon.size_px[1],
            }
            self.world_state_ready.emit(world_state)
            
            elapsed = time.perf_counter() - loop_start
            sleep_time = dt - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def stop(self):
        self.running = False
        self.wait()


class VideoPlaybackWorker(QThread):
    raw_frame_ready = Signal(np.ndarray, dict)
    
    def __init__(self, video_path: str):
        super().__init__()
        self.video_path = video_path
        self.running = False
        self.paused = False
        
    def command_velocity(self, vx, vy):
        pass
        
    def command_position(self, px, py, snap=False):
        pass

    def run(self):
        self.running = True
        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            self.running = False
            return
            
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0: fps = 30.0
        dt = 1.0 / fps
        
        while self.running:
            if self.paused:
                time.sleep(0.1)
                continue
                
            loop_start = time.perf_counter()
            ret, bgr = cap.read()
            if not ret:
                # Loop video
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
                
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if len(bgr.shape) == 3 else bgr
            
            # Create dummy ground truth so ProcessingWorker doesn't crash
            gt = {
                "beacon_x": 0.0,
                "beacon_y": 0.0,
                "gimbal_x": 0.0,
                "gimbal_y": 0.0,
                "dt": dt
            }
            self.raw_frame_ready.emit(gray, gt)
            
            elapsed = time.perf_counter() - loop_start
            sleep_time = dt - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
                
        cap.release()

    def stop(self):
        self.running = False
        self.wait()


class ProcessingWorker(QThread):
    processed_frame_ready = Signal(np.ndarray)
    stats_updated = Signal(dict)
    
    def __init__(self, config: AppConfig, sim_worker: SimWorker):
        super().__init__()
        self.cfg = config
        self.sim_worker = sim_worker
        self.sim_worker.proc_worker = self  # Inject for world_state reading
        self.running = False
        self.current_state = "IDLE"  # NEW: Track current state for world view
        
        self.ai_verifier = AIVerifier("models/patch_verifier_cnn.onnx")
        self.kf = KalmanFilterCV(dt=1.0/60.0)
        self.sm = StateMachine(lock_threshold_px=self.cfg.estimation.lock_threshold_px,
                               required_lock_frames=self.cfg.estimation.lock_frames)
        # max_output driven by actual gimbal velocity cap (resolved at runtime from cfg)
        gimbal_max_v = (self.cfg.camera.gimbal.max_pan_rate_deg_s
                        * (self.cfg.camera.resolution[0] / self.cfg.camera.fov_deg[0])
                        / 60.0)  # px/frame at 60 fps
        self.pid_x = PIDController(self.cfg.control.kp, self.cfg.control.ki,
                                   self.cfg.control.kd, gimbal_max_v, dt=1.0/60.0)
        self.pid_y = PIDController(self.cfg.control.kp, self.cfg.control.ki,
                                   self.cfg.control.kd, gimbal_max_v, dt=1.0/60.0)
        
        bx, by = self.cfg.environment.world_size[0]/2, self.cfg.environment.world_size[1]/2
        # NEW: Pass world bounds AND FOV dims to spiral search for proper clamping
        self.search = SpiralSearch(
            bx, by, 
            fov_size=self.cfg.camera.resolution[1],
            world_bounds=tuple(self.cfg.environment.world_size),
            fov_dims=tuple(self.cfg.camera.resolution)
        )
        self.raster = RasterSearch(
            bx, by,
            search_w=float(self.cfg.environment.world_size[0]) * 0.9,
            search_h=float(self.cfg.environment.world_size[1]) * 0.9,
            col_spacing=300.0,   # ~half FOV width (640px) for overlap
            row_spacing=200.0,   # ~half FOV height (480px) for overlap
            dwell_time=0.25,     # 0.25s per point = ~15 frames at 60Hz
            world_bounds=tuple(self.cfg.environment.world_size),
            fov_dims=tuple(self.cfg.camera.resolution)
        )
        self._spiral_time = 0.0
        self._spiral_max_time = 4.0   # seconds; switch to raster after this
        self._use_raster = False
        self._last_known_x = bx
        self._last_known_y = by
        
        self.latest_data = None
        self.mutex = QMutex()
        
    def on_raw_frame(self, frame, gt):
        with QMutexLocker(self.mutex):
            self.latest_data = (frame, gt)
            
    def run(self):
        self.running = True
        self.sm.start_search()
        last_frame_time = time.perf_counter()
        
        while self.running:
            with QMutexLocker(self.mutex):
                data = self.latest_data
                self.latest_data = None
                
            if data is None:
                time.sleep(0.005)
                continue
                
            process_start = time.perf_counter()
            
            frame, gt = data
            dt = gt["dt"]
            
            # Weather & Jitter Disturbances
            degraded = apply_weather_degradation(frame, self.cfg.disturbances.weather_preset)
            noisy = apply_sensor_noise(
                degraded, 
                self.cfg.disturbances.gaussian_sigma, 
                self.cfg.disturbances.poisson, 
                self.cfg.disturbances.salt_and_pepper_percent
            )
            
            candidates = extract_candidates(noisy)

            # ── Size Discriminator ──
            # Filter candidates to those whose bounding box matches the target size,
            # which perfectly rejects random noise blobs.
            target_sz = self.cfg.beacon.target_size_px
            ref_w = target_sz[0] if target_sz[0] > 0 else self.cfg.beacon.size_px[0]
            ref_h = target_sz[1] if target_sz[1] > 0 else self.cfg.beacon.size_px[1]
            candidates = size_discriminate(
                candidates, ref_w, ref_h,
                tolerance=self.cfg.beacon.size_tolerance
            )
            
            valid_det = False
            err = float('inf')
            dw_x, dw_y = 0.0, 0.0
            best_score = 0.0
            
            # Convert to BGR for drawing colored overlays
            display_frame = cv2.cvtColor(noisy, cv2.COLOR_GRAY2BGR)
            
            if len(candidates) > 0:
                centroids = []
                for cand in candidates:
                    cx, cy = calculate_centroid(noisy, cand)
                    centroids.append((cx, cy))
                    
                scores = self.ai_verifier.extract_and_verify(noisy, centroids)
                
                # ── Classical fallback when ONNX model is absent ─────────────
                # If AI verifier is disabled (model not found), scores are all 0.0.
                # In that case, fall back to using the candidate with the best
                # intensity-weighted area (largest bright blob) as the target.
                ai_active = any(s > 0.1 for s in scores)
                
                best_idx = -1
                if ai_active:
                    # AI path: pick highest score above threshold
                    for i, score in enumerate(scores):
                        if score > 0.5 and score > best_score:
                            best_score = score
                            best_idx = i
                else:
                    # Classical path: pick candidate with largest area
                    best_area = 0
                    for i, cand in enumerate(candidates):
                        x, y, w, h, *_ = cand
                        area = w * h
                        if area > best_area:
                            best_area = area
                            best_idx = i
                            best_score = 0.6  # Synthetic confidence for classical mode
                
                if best_idx != -1:
                    cx, cy = centroids[best_idx]
                    
                    # FIXED: Use correct viewport bounds calculation
                    # Viewport bounds: gimbal center ± (width/2, height/2)
                    gx, gy = gt["gimbal_x"], gt["gimbal_y"]
                    viewport_w = self.cfg.camera.resolution[0]
                    viewport_h = self.cfg.camera.resolution[1]
                    left = gx - viewport_w / 2.0
                    top = gy - viewport_h / 2.0
                    w_x = left + cx
                    w_y = top + cy
                    dw_x, dw_y = w_x, w_y
                    valid_det = True
                    # Tracking error is the distance from the target to the center of the FOV
                    err = math.hypot(cx - viewport_w / 2.0, cy - viewport_h / 2.0)
                    
                    # Draw AI Detection bounding box
                    cv2.rectangle(display_frame, (int(cx)-16, int(cy)-16), (int(cx)+16, int(cy)+16), (0, 255, 0), 2)
                    
            self.kf.predict()
            if valid_det:
                valid_det = self.kf.update(dw_x, dw_y)
            
            # Track previous state for transition detection
            prev_state = self.sm.state
            state = self.sm.update(valid_det, err)
            self.current_state = state  # NEW: Store for world view
            
            # NEW: If transitioning from LOST → SEARCH, reset to last known position
            # and reset Kalman so stale velocity doesn't bias next REACQUIRE slew.
            if prev_state == TrackingState.LOST and state == TrackingState.SEARCH:
                self.search.reset(self._last_known_x, self._last_known_y)
                self.raster.reset(self._last_known_x, self._last_known_y)
                self._spiral_time = 0.0
                self._use_raster = False
                self.sim_worker.command_position(self._last_known_x, self._last_known_y)
                self.pid_x.reset()
                self.pid_y.reset()
                self.kf.reset()
                
            # Control Logic
            if state == TrackingState.SEARCH:
                # Phase 1: spiral from last known; Phase 2: raster for full coverage
                self._spiral_time += dt
                if self._spiral_time > self._spiral_max_time and not self._use_raster:
                    self._use_raster = True
                    self.raster.reset(self._last_known_x, self._last_known_y)
                if self._use_raster:
                    sx, sy = self.raster.step(dt)
                else:
                    sx, sy = self.search.step(dt)
                self.sim_worker.command_position(sx, sy)
            elif state == TrackingState.REACQUIRE:
                # REACQUIRE: Slew to KF predicted position (not blind spiral).
                # Also update last known position and reset search state.
                px, py = self.kf.get_position()
                self._last_known_x, self._last_known_y = px, py
                self._spiral_time = 0.0
                self._use_raster = False
                self.search.reset(px, py)
                
                kv_x, kv_y = self.kf.get_velocity()
                vx = self.pid_x.compute(px - gt["gimbal_x"]) + (kv_x * (1.0 / 60.0))
                vy = self.pid_y.compute(py - gt["gimbal_y"]) + (kv_y * (1.0 / 60.0))
                self.sim_worker.command_velocity(vx, vy)
            elif state in [TrackingState.ACQUIRE, TrackingState.LOCKED, TrackingState.COAST]:
                px, py = self.kf.get_position()
                
                if prev_state in [TrackingState.SEARCH, TrackingState.LOST]:
                    # User requested: "when we acquire the beacon at first can we put trackers center exactly on beacon"
                    self.sim_worker.command_position(px, py, snap=True)
                    self.pid_x.reset()
                    self.pid_y.reset()
                else:
                    # Update last known position continuously while tracking is good
                    gx_now, gy_now = gt["gimbal_x"], gt["gimbal_y"]
                    self._last_known_x, self._last_known_y = gx_now, gy_now
                    self._spiral_time = 0.0
                    self._use_raster = False
                    self.search.reset(gx_now, gy_now)
                    
                    kv_x, kv_y = self.kf.get_velocity()
                    vx = self.pid_x.compute(px - gt["gimbal_x"]) + (kv_x * (1.0 / 60.0))
                    vy = self.pid_y.compute(py - gt["gimbal_y"]) + (kv_y * (1.0 / 60.0))
                    self.sim_worker.command_velocity(vx, vy)
                
                # Draw Kalman state crosshair and covariance ellipse
                kx = px - gt["gimbal_x"] + self.cfg.camera.resolution[0]/2
                ky = py - gt["gimbal_y"] + self.cfg.camera.resolution[1]/2
                cv2.drawMarker(display_frame, (int(kx), int(ky)), (0, 0, 255), cv2.MARKER_CROSS, 20, 2)
                
                # Draw Gimbal Boresight (fixed center crosshair)
                cx_center = int(self.cfg.camera.resolution[0] // 2)
                cy_center = int(self.cfg.camera.resolution[1] // 2)
                cv2.drawMarker(display_frame, (cx_center, cy_center), (255, 255, 255), cv2.MARKER_CROSS, 40, 1)
                
                radius = int(math.sqrt(self.kf.P[0,0] + self.kf.P[2,2]) * 2)
                if radius > 0:
                    cv2.circle(display_frame, (int(kx), int(ky)), min(radius, 100), (0, 255, 255), 1)
                
            # Render State
            cv2.putText(display_frame, state.name, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)

            process_end = time.perf_counter()
            latency_ms = (process_end - process_start) * 1000.0
            fps = 1.0 / (process_end - last_frame_time + 1e-6)
            last_frame_time = process_end

            self.processed_frame_ready.emit(display_frame)
            stats = {
                "state": state.name,
                "error": err,
                "gimbal_x": gt["gimbal_x"],
                "gimbal_y": gt["gimbal_y"],
                "target_x": gt["beacon_x"],
                "target_y": gt["beacon_y"],
                "confidence": best_score * 100.0,
                "latency_ms": latency_ms,
                "fps": fps
            }
            self.stats_updated.emit(stats)

    def stop(self):
        self.running = False
        self.wait()
