"""
scenario_runner.py — LaserPAT simulation orchestrator.

Canonical pipeline (one clean causal chain per frame):
    Scenario → World → Platform/Gimbal → DisturbanceState → SensorFrame
    → PerceptionResult → CandidateManager → TargetIdentity
    → PATSupervisor → PATCommand → ServoLoop → next frame

The runner is an orchestrator, not an algorithm.  All algorithmic logic
lives in the subsystem classes it coordinates.  Adding a new subsystem
does NOT require modifying this file — it requires adding a new class
that plugs into the pipeline at the appropriate step.
"""

import argparse
import time
import math
import os
from datetime import datetime
import numpy as np

from src.config import load_config

# Environment
from src.environment.world import World
from src.environment.motion import (
    StraightMotion, CircularMotion, Figure8Motion, RandomWalkMotion
)
from src.environment.beacon import Beacon
from src.environment.platform import Platform

# Camera
from src.camera.viewport import Viewport
from src.camera.gimbal import Gimbal
from src.camera.sensor import Sensor
from src.camera.camera_source import SyntheticCameraSource

# Disturbance (unified model)
from src.disturbances.disturbance_model import DisturbanceModel

# Perception (unified interface — resolves dual-AI-path conflict)
from src.detection.perception import build_perception
from src.detection.candidate_manager import CandidateManager

# Estimation + PAT control
from src.estimation.pat_supervisor import PATSupervisor
from src.estimation.handoff import evaluate_handoff

# Actuator
from src.control.servo_loop import ServoLoop

# Logging
from src.logging.csv_logger import CSVLogger, FrameRecord


def run_scenario(config_path: str, headless: bool = True, output_csv: str = None):
    cfg = load_config(config_path)

    # ------------------------------------------------------------------
    # 1.  World / environment setup
    # ------------------------------------------------------------------
    world = World(*cfg.environment.world_size)
    world_center_x = cfg.environment.world_size[0] / 2
    world_center_y = cfg.environment.world_size[1] / 2

    # --- Beacon initial position ---
    loc = cfg.beacon.initial_location
    if loc == "random":
        import random
        bx = random.uniform(100, cfg.environment.world_size[0] - 100)
        by = random.uniform(100, cfg.environment.world_size[1] - 100)
    elif loc == "center":
        bx, by = world_center_x, world_center_y
    elif loc == "top-left":
        bx, by = 200.0, 200.0
    elif loc == "top-right":
        bx, by = cfg.environment.world_size[0] - 200.0, 200.0
    elif loc == "bottom-left":
        bx, by = 200.0, cfg.environment.world_size[1] - 200.0
    elif loc == "bottom-right":
        bx = cfg.environment.world_size[0] - 200.0
        by = cfg.environment.world_size[1] - 200.0
    else:
        bx, by = world_center_x, world_center_y

    # --- Beacon motion ---
    motion_type = cfg.beacon.motion.lower()
    if motion_type == "straight":
        import random
        angle = random.uniform(0, 2 * math.pi)
        bmotion = StraightMotion((bx, by), speed=0.5, angle_rad=angle)
    elif motion_type == "circular":
        bmotion = CircularMotion((world_center_x, world_center_y), radius=150.0, angular_speed=0.005)
    elif motion_type in ("figure8", "figure_8"):
        bmotion = Figure8Motion((world_center_x, world_center_y), width=200.0, height=150.0, speed=0.01)
    elif motion_type in ("random", "random_walk"):
        bmotion = RandomWalkMotion((bx, by), max_step=1.5)
    else:
        raise ValueError(
            f"Unknown beacon motion type: {motion_type!r}. "
            f"Must be one of: straight, circular, figure8, random"
        )

    beacon = Beacon(cfg.beacon.shape, cfg.beacon.size_px, bmotion)

    # --- Platform (stationary relative to world by default) ---
    pmotion  = StraightMotion((bx, by), speed=0.0)
    platform = Platform(pmotion, jitter_max_px=cfg.disturbances.max_displacement_px)

    # --- Distractor beacons (multi-beacon scenario support) ---
    distractors = _build_distractors(cfg, world_center_x, world_center_y)

    # ------------------------------------------------------------------
    # 2.  Camera subsystem
    # ------------------------------------------------------------------
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
    camera = SyntheticCameraSource(sensor, beacon, distractors)

    # ------------------------------------------------------------------
    # 3.  Disturbance model (replaces independent per-subsystem generators)
    # ------------------------------------------------------------------
    disturb_model = DisturbanceModel(cfg, link_distance_km=1.0)

    # ------------------------------------------------------------------
    # 4.  Perception (resolves the dual AI path conflict)
    # ------------------------------------------------------------------
    perception   = build_perception(cfg)
    cand_manager = CandidateManager()

    # ------------------------------------------------------------------
    # 5.  PAT supervisor (wraps KF + StateMachine + PID + search)
    # ------------------------------------------------------------------
    dt         = 1.0 / 30.0
    supervisor = PATSupervisor(cfg, dt=dt)
    supervisor.start_search()

    # ------------------------------------------------------------------
    # 6.  Actuator (ServoLoop — now actually wired into the pipeline)
    # ------------------------------------------------------------------
    servo = ServoLoop(gimbal)

    # ------------------------------------------------------------------
    # 7.  Logging setup
    # ------------------------------------------------------------------
    if output_csv is None:
        timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_csv = f"logs/run_{cfg.scenario_name.replace(' ', '_')}_{timestamp}.csv"
    os.makedirs(os.path.dirname(output_csv) or "logs", exist_ok=True)

    frames    = int(cfg.duration_seconds * 30)
    start_time = time.time()

    # ------------------------------------------------------------------
    # 8.  Main simulation loop  (one clean causal chain per frame)
    # ------------------------------------------------------------------
    with CSVLogger(output_csv) as logger:
        for frame_idx in range(frames):

            # ── Step 1: Advance world state ──────────────────────────────
            beacon.step(dt)
            platform.step(dt)
            for d in distractors:
                d.step(dt)

            # ── Step 2: Compute unified disturbance state ─────────────────
            d_state = disturb_model.step(platform)

            # ── Step 3: Capture + apply disturbances ──────────────────────
            raw_frame      = camera.capture_frame()
            disturbed_frame = disturb_model.apply_to_frame(raw_frame, d_state)

            # ── Step 4: Perceive ──────────────────────────────────────────
            frame_start    = time.time()
            percept_result = perception.run(disturbed_frame, frame_id=frame_idx)

            # ── Step 5: Candidate management ─────────────────────────────
            identity = cand_manager.update(percept_result)

            # ── Step 6: PAT supervisor → command ─────────────────────────
            gx, gy = gimbal.get_position()
            cmd    = supervisor.step(identity, gimbal_x=gx, gimbal_y=gy)

            # ── Step 7: Actuate (ServoLoop is now in the pipeline) ────────
            if cmd.mode == "VELOCITY":
                servo.command_velocity(cmd.x, cmd.y)
            elif cmd.mode == "POSITION":
                servo.command_position(cmd.x, cmd.y)
            else:
                servo.hold()
            servo.step(dt)

            # ── Step 8: Coarse-to-fine handoff evaluation ─────────────────
            tracking_error_px = _compute_tracking_error(identity, beacon)
            handoff = evaluate_handoff(
                supervisor,
                cfg.link_budget_model,
                tracking_error_px=tracking_error_px,
                fov_deg=cfg.camera.fov_deg[0],
                res_px=cfg.camera.resolution[0],
            )

            # ── Step 9: Log frame ─────────────────────────────────────────
            ai_score     = identity.candidate.ai_confidence if identity and identity.is_valid else 0.0
            frame_time   = time.time() - frame_start
            gx_post, gy_post = gimbal.get_position()

            record = FrameRecord(
                frame_id=frame_idx,
                timestamp=frame_idx * dt,
                state=cmd.pat_state,
                tracking_error_px=tracking_error_px if math.isfinite(tracking_error_px) else 0.0,
                gimbal_x=gx_post,
                gimbal_y=gy_post,
                target_x=beacon.x,
                target_y=beacon.y,
                ai_score=ai_score,
                weather_preset=cfg.disturbances.weather_preset,
                innovation_gate_passed=True,
            )
            logger.log_frame(record)

            if not headless and frame_idx % 30 == 0:
                print(
                    f"Frame {frame_idx:5d} | State: {cmd.pat_state:<10} "
                    f"| Err: {tracking_error_px:.2f}px "
                    f"| Backend: {percept_result.backend_used} "
                    f"| Link: {handoff.link_status} ({handoff.margin_dB:.1f} dB margin)"
                )

    total_time = time.time() - start_time
    avg_fps    = frames / total_time if total_time > 0 else 0

    print(f"Scenario completed. Final state: {supervisor.state.name}")
    print(f"CSV log written to: {output_csv}")
    print(f"Total time: {total_time:.2f}s | Avg FPS: {avg_fps:.1f}")

    return output_csv


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_tracking_error(identity, beacon) -> float:
    """Return Euclidean error between detected centroid and beacon ground truth."""
    if identity is not None and identity.is_valid:
        return math.hypot(
            identity.candidate.cx - beacon.x,
            identity.candidate.cy - beacon.y,
        )
    return float('inf')


def _build_distractors(cfg, world_cx: float, world_cy: float):
    """Instantiate distractor beacons from config."""
    import math as _math, random as _random
    distractors = []
    for dc in getattr(cfg.beacon, 'distractors', []):
        loc = dc.initial_location
        if loc == "random":
            dx = _random.uniform(100, cfg.environment.world_size[0] - 100)
            dy = _random.uniform(100, cfg.environment.world_size[1] - 100)
        else:
            dx, dy = world_cx, world_cy

        dmotion = StraightMotion(
            (dx, dy),
            speed=0.5,
            angle_rad=_random.uniform(0, 2 * _math.pi),
        )
        distractors.append(Beacon(dc.shape, dc.size_px, dmotion))
    return distractors


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

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
