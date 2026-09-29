"""
video_runner.py — Headless video-file runner for LaserPAT.

Reads an .mp4 / .avi file frame-by-frame, runs the *same* canonical
Detect → CandidateManager → PATSupervisor → Control pipeline used by
scenario_runner.py.  This ensures Desktop result == Video result.

Entry point
-----------
    run_video(video_path, config_path, output_csv)

CLI
---
    python -m src.modes.video_runner \\
        --video path/to/clip.mp4 \\
        --config configs/default.yaml \\
        --output logs/video_run.csv
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

from src.config import load_config

# Unified perception pipeline (shared with scenario_runner)
from src.camera.camera_source import VideoCameraSource
from src.detection.perception import build_perception
from src.detection.candidate_manager import CandidateManager
from src.estimation.pat_supervisor import PATSupervisor
from src.estimation.state_machine import TrackingState
from src.logging.csv_logger import CSVLogger, FrameRecord


# (helper _to_grayscale is now inside VideoCameraSource)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_video(
    video_path: str,
    config_path: str = "configs/default.yaml",
    output_csv: str | None = None,
    *,
    verbose: bool = True,
) -> str:
    """
    Process a pre-recorded video through the LaserPAT pipeline.

    Parameters
    ----------
    video_path:  Path to the .mp4 / .avi file.
    config_path: YAML config controlling detection / estimation / control.
    output_csv:  Destination for the per-frame CSV log.  If None a path is
                 auto-generated under ``logs/`` next to the video file.
    verbose:     Print progress every 30 frames when True.

    Returns
    -------
    Path to the written CSV file.
    """
    cfg = load_config(config_path)

    # ------------------------------------------------------------------
    # Resolve output path
    # ------------------------------------------------------------------
    if output_csv is None:
        stem = Path(video_path).stem
        os.makedirs("logs", exist_ok=True)
        output_csv = os.path.join("logs", f"{stem}_{int(time.time())}.csv")

    # ------------------------------------------------------------------
    # Open video via CameraSource abstraction
    # ------------------------------------------------------------------
    with VideoCameraSource(video_path, grayscale=True) as cam:
        fps          = cam.fps
        total_frames = cam.total_frames
        frame_w      = cam.frame_width
        frame_h      = cam.frame_height
        dt           = 1.0 / fps

        if verbose:
            print(
                f"[VideoRunner] {video_path}  "
                f"{frame_w}×{frame_h} @ {fps:.1f} fps  "
                f"({total_frames} frames)"
            )

        # ------------------------------------------------------------------
        # Initialise shared pipeline components
        # ------------------------------------------------------------------
        perception   = build_perception(cfg)          # same factory as scenario_runner
        cand_manager = CandidateManager()             # same class as scenario_runner

        # Virtual gimbal position (video mode — no real gimbal)
        gim_x, gim_y = frame_w / 2.0, frame_h / 2.0

        # PATSupervisor needs environment world_size; use frame dims as world
        # We patch cfg.environment.world_size to match video frame dims
        cfg.environment.world_size = (frame_w, frame_h)
        supervisor = PATSupervisor(cfg, dt=dt)
        supervisor.start_search()

        # ------------------------------------------------------------------
        # Main loop
        # ------------------------------------------------------------------
        t_start   = time.perf_counter()
        frame_idx = 0

        with CSVLogger(output_csv) as logger:
            while cam.is_available():
                gray = cam.capture_frame()
                if gray is None:
                    break

                timestamp = frame_idx * dt

                # ── Perceive (shared pipeline) ─────────────────────────
                percept_result = perception.run(gray, frame_id=frame_idx)

                # ── Candidate management (shared pipeline) ─────────────
                identity = cand_manager.update(percept_result)

                # ── PAT supervisor (shared pipeline) ───────────────────
                cmd = supervisor.step(identity, gimbal_x=gim_x, gimbal_y=gim_y)

                # Apply virtual gimbal from command
                if cmd.mode == "POSITION":
                    # Slew at max rate (5% of frame per step)
                    max_v = max(frame_w, frame_h) * 0.05
                    dx = cmd.x - gim_x
                    dy = cmd.y - gim_y
                    dist = math.hypot(dx, dy)
                    if dist > 0:
                        step = min(dist, max_v)
                        gim_x += (dx / dist) * step
                        gim_y += (dy / dist) * step
                elif cmd.mode == "VELOCITY":
                    gim_x = float(np.clip(gim_x + cmd.x, 0, frame_w - 1))
                    gim_y = float(np.clip(gim_y + cmd.y, 0, frame_h - 1))

                # ── Extract telemetry for log ───────────────────────────
                ai_score = (
                    identity.candidate.ai_confidence
                    if identity and identity.is_valid else 0.0
                )
                det_x = identity.candidate.cx if identity and identity.is_valid else 0.0
                det_y = identity.candidate.cy if identity and identity.is_valid else 0.0
                euclidean_error = (
                    math.hypot(det_x - gim_x, det_y - gim_y)
                    if identity and identity.is_valid else float("inf")
                )

                # ── Log ────────────────────────────────────────────────
                record = FrameRecord(
                    frame_id=frame_idx,
                    timestamp=round(timestamp, 4),
                    state=cmd.pat_state,
                    tracking_error_px=round(euclidean_error, 3) if not math.isinf(euclidean_error) else -1.0,
                    gimbal_x=round(gim_x, 2),
                    gimbal_y=round(gim_y, 2),
                    target_x=round(det_x, 2),
                    target_y=round(det_y, 2),
                    ai_score=round(ai_score, 4),
                    weather_preset=cfg.disturbances.weather_preset,
                    innovation_gate_passed=(identity is not None and identity.is_valid),
                )
                logger.log_frame(record)

                if verbose and frame_idx % 30 == 0:
                    elapsed = time.perf_counter() - t_start
                    pct = (frame_idx / total_frames * 100) if total_frames > 0 else 0
                    print(
                        f"  [{pct:5.1f}%] frame {frame_idx:5d} | "
                        f"state={cmd.pat_state:<10} | "
                        f"backend={percept_result.backend_used} | "
                        f"err={euclidean_error:7.2f}px | elapsed={elapsed:.1f}s"
                    )

                frame_idx += 1

    elapsed_total = time.perf_counter() - t_start
    if verbose:
        print(
            f"[VideoRunner] Done - {frame_idx} frames in {elapsed_total:.2f}s "
            f"({frame_idx / elapsed_total:.1f} fps processing)\n"
            f"  CSV  -> {output_csv}"
        )

    return output_csv


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="video_runner",
        description="LaserPAT headless video processor — runs Detect→KF→Control on a .mp4/.avi file.",
    )
    p.add_argument("--video", required=True, help="Input video file (.mp4 or .avi)")
    p.add_argument(
        "--config",
        default="configs/default.yaml",
        help="YAML config path (default: configs/default.yaml)",
    )
    p.add_argument(
        "--output",
        default=None,
        help="Output CSV path (auto-generated under logs/ if omitted)",
    )
    p.add_argument("--quiet", action="store_true", help="Suppress progress output")
    return p


if __name__ == "__main__":
    args = _build_parser().parse_args()
    csv_out = run_video(
        video_path=args.video,
        config_path=args.config,
        output_csv=args.output,
        verbose=not args.quiet,
    )
    print(f"Output: {csv_out}")
    sys.exit(0)
