"""
video_runner.py — Headless video-file runner for LaserPAT.

Reads an .mp4 / .avi file frame-by-frame, runs the full
Detect → KF → Control pipeline, and writes a per-frame CSV log.

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

import cv2
import numpy as np

from src.config import load_config
from src.detection.classical import extract_candidates, calculate_centroid
from src.detection.ai_verifier import AIVerifier
from src.estimation.kalman import KalmanFilterCV
from src.estimation.state_machine import StateMachine, TrackingState
from src.control.pid import PIDController
from src.control.search_patterns import SpiralSearch
from src.logging.csv_logger import CSVLogger, FrameRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_grayscale(frame: np.ndarray) -> np.ndarray:
    """Convert BGR / BGRA / already-gray frame to uint8 2-D array."""
    if frame.ndim == 2:
        return frame
    if frame.shape[2] == 4:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


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
    # Open video
    # ------------------------------------------------------------------
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video file: {video_path!r}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    dt = 1.0 / fps

    if verbose:
        print(
            f"[VideoRunner] {video_path}  "
            f"{frame_w}×{frame_h} @ {fps:.1f} fps  "
            f"({total_frames} frames)"
        )

    # ------------------------------------------------------------------
    # Initialise pipeline components (no GUI)
    # ------------------------------------------------------------------
    # ONNX model path — try both relative and exe-local locations
    onnx_candidates = [
        "models/patch_verifier_cnn.onnx",
        os.path.join(os.path.dirname(__file__), "..", "..", "models", "patch_verifier_cnn.onnx"),
    ]
    onnx_path = next((p for p in onnx_candidates if os.path.exists(p)), onnx_candidates[0])

    use_verifier = cfg.detection.use_cnn_verifier and os.path.exists(onnx_path)
    ai_verifier = AIVerifier(onnx_path) if use_verifier else None

    kf = KalmanFilterCV(dt=dt)
    sm = StateMachine(
        lock_threshold_px=cfg.estimation.lock_threshold_px,
        required_lock_frames=cfg.estimation.lock_frames,
    )

    # Gimbal virtual position — centre of frame initially
    gim_x, gim_y = frame_w / 2.0, frame_h / 2.0
    max_v = max(frame_w, frame_h) * 0.05  # 5 % of frame per step

    pid_x = PIDController(cfg.control.kp, cfg.control.ki, cfg.control.kd, max_v)
    pid_y = PIDController(cfg.control.kp, cfg.control.ki, cfg.control.kd, max_v)
    search = SpiralSearch(gim_x, gim_y, fov_size=min(frame_w, frame_h))

    sm.start_search()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    t_start = time.perf_counter()
    frame_idx = 0

    with CSVLogger(output_csv) as logger:
        while True:
            ret, bgr = cap.read()
            if not ret:
                break

            gray = _to_grayscale(bgr)
            timestamp = frame_idx * dt

            # ---- Detection ------------------------------------------
            candidates = extract_candidates(gray)
            valid_detection = False
            det_x = det_y = 0.0
            euclidean_error = float("inf")
            ai_score = 0.0

            if candidates:
                centroids = [calculate_centroid(gray, c) for c in candidates]

                if ai_verifier is not None:
                    scores = ai_verifier.extract_and_verify(gray, centroids)
                else:
                    # Fallback: treat every candidate as equally probable
                    scores = [0.6] * len(centroids)

                best_score = 0.0
                best_idx = -1
                for i, s in enumerate(scores):
                    if s > 0.5 and s > best_score:
                        best_score = s
                        best_idx = i

                if best_idx != -1:
                    det_x, det_y = centroids[best_idx]
                    valid_detection = True
                    ai_score = best_score
                    euclidean_error = math.hypot(det_x - gim_x, det_y - gim_y)

            # ---- Estimation -----------------------------------------
            kf.predict()
            if valid_detection:
                valid_detection = kf.update(det_x, det_y)

            state = sm.update(valid_detection, euclidean_error)

            # ---- Control --------------------------------------------
            if state == TrackingState.SEARCH:
                sx, sy = search.step(dt)
                gim_x, gim_y = sx, sy
            else:
                search.reset(gim_x, gim_y)
                pred_x, pred_y = kf.get_position()
                vx = pid_x.compute(pred_x - gim_x)
                vy = pid_y.compute(pred_y - gim_y)
                gim_x = np.clip(gim_x + vx, 0, frame_w - 1)
                gim_y = np.clip(gim_y + vy, 0, frame_h - 1)

            # ---- Log ------------------------------------------------
            record = FrameRecord(
                frame_id=frame_idx,
                timestamp=round(timestamp, 4),
                state=state.name,
                tracking_error_px=round(euclidean_error, 3) if not math.isinf(euclidean_error) else -1.0,
                gimbal_x=round(gim_x, 2),
                gimbal_y=round(gim_y, 2),
                target_x=round(det_x, 2),
                target_y=round(det_y, 2),
                ai_score=round(ai_score, 4),
                weather_preset=cfg.disturbances.weather_preset,
                innovation_gate_passed=valid_detection or (euclidean_error == float("inf")),
            )
            logger.log_frame(record)

            if verbose and frame_idx % 30 == 0:
                elapsed = time.perf_counter() - t_start
                pct = (frame_idx / total_frames * 100) if total_frames > 0 else 0
                print(
                    f"  [{pct:5.1f}%] frame {frame_idx:5d} | "
                    f"state={state.name:<8} | err={euclidean_error:7.2f}px | "
                    f"elapsed={elapsed:.1f}s"
                )

            frame_idx += 1

    cap.release()

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
