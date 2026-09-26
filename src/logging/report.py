"""
report.py - Generates a plain-text / Markdown evaluation summary from a
completed CSV log file.

Usage:
    python -m src.logging.report logs/run_20240101.csv
"""
import csv
import math
import sys
from dataclasses import dataclass
from typing import List


@dataclass
class RunSummary:
    # 6 Mandatory Benchmark Outputs (from SPEC.md)
    acquisition_time_s: float
    mean_error_px: float
    max_error_px: float
    rmse_px: float
    target_loss_rate_pct: float
    reacquisition_time_s: float
    lock_retention_rate_pct: float
    min_fps: float
    mean_fps: float
    
    # Additional context
    total_frames: int
    scenario: str = "unknown"

    def to_markdown(self) -> str:
        lines = [
            "# LaserPAT Run Report",
            "",
            f"**Scenario:** `{self.scenario}`",
            f"**Total Frames:** {self.total_frames}",
            "",
            "## 6 Mandatory Benchmark Metrics (SPEC.md)",
            "",
            f"| Metric | Value | Gate Requirement |",
            f"|--------|-------|------------------|",
            f"| 1. Acquisition Time | {self.acquisition_time_s:.3f} s | <= 2.0 s |",
            f"| 2. Tracking Error (Mean) | {self.mean_error_px:.2f} px | - |",
            f"| 2. Tracking Error (RMS) | {self.rmse_px:.2f} px | <= 10 px |",
            f"| 2. Tracking Error (Max) | {self.max_error_px:.2f} px | - |",
            f"| 3. Target Loss Rate | {self.target_loss_rate_pct:.1f} % | < 5 % |",
            f"| 4. Re-acquisition Time | {self.reacquisition_time_s:.3f} s | <= 1.0 s |",
            f"| 5. Lock Retention Rate | {self.lock_retention_rate_pct:.1f} % | - |",
            f"| 6. Processing Speed (Min) | {self.min_fps:.1f} FPS | >= 20 FPS |",
            f"| 6. Processing Speed (Mean) | {self.mean_fps:.1f} FPS | - |",
            "",
            "## Pass/Fail Status",
            "",
            self._gate_status(),
        ]
        return "\n".join(lines)
    
    def _gate_status(self) -> str:
        checks = [
            ("Acquisition Time <= 2s", self.acquisition_time_s <= 2.0),
            ("RMS Error <= 10px", self.rmse_px <= 10.0),
            ("Target Loss < 5%", self.target_loss_rate_pct < 5.0),
            ("Re-acquisition <= 1s", self.reacquisition_time_s <= 1.0),
            ("Min FPS >= 20", self.min_fps >= 20.0),
        ]
        
        lines = []
        all_pass = True
        for check, passed in checks:
            status = "[PASS] PASS" if passed else "[FAIL] FAIL"
            lines.append(f"- {check}: {status}")
            if not passed:
                all_pass = False
        
        lines.append("")
        if all_pass:
            lines.append("** SLICE GATE: PASSED**")
        else:
            lines.append("** SLICE GATE: FAILED - Fix above issues**")
        
        return "\n".join(lines)


def summarise_log(csv_path: str, scenario: str = "unknown") -> RunSummary:
    """
    Calculate the 6 mandatory benchmark metrics from SPEC.md:
    1. Acquisition Time (s) - time from start to first LOCKED
    2. Tracking Error - mean, RMS, max (px)
    3. Target Loss Rate (%) - frames not tracking
    4. Re-acquisition Time (s) - time from LOST to LOCKED
    5. Lock Retention Rate (%) - frames in LOCKED after initial acquisition
    6. Processing Speed (FPS) - min and mean
    """
    errors: List[float] = []
    states: List[str] = []
    timestamps: List[float] = []
    total = 0
    
    first_lock_time = None
    locked_frames_after_first_lock = 0
    frames_after_first_lock = 0
    
    loss_events = []  # List of (lost_time, reacquired_time)
    current_loss_start = None
    
    frame_times: List[float] = []

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        prev_timestamp = 0.0
        
        for row in reader:
            total += 1
            state = row.get("state", "")
            states.append(state)
            
            timestamp = float(row.get("timestamp", 0.0))
            timestamps.append(timestamp)
            
            # Calculate frame time (processing duration)
            if prev_timestamp > 0:
                frame_time = timestamp - prev_timestamp
                if frame_time > 0:
                    frame_times.append(1.0 / frame_time)  # FPS for this frame
            prev_timestamp = timestamp
            
            err_str = row.get("tracking_error_px", "")
            try:
                err = float(err_str)
            except (ValueError, TypeError):
                err = None

            # Track acquisition time (first LOCKED)
            if state == "LOCKED" and first_lock_time is None:
                first_lock_time = timestamp
            
            # Count locked frames after acquisition
            if first_lock_time is not None:
                frames_after_first_lock += 1
                if state == "LOCKED":
                    locked_frames_after_first_lock += 1
            
            # Track loss/reacquisition events
            if state == "LOST" and current_loss_start is None:
                current_loss_start = timestamp
            elif state == "LOCKED" and current_loss_start is not None:
                loss_events.append((current_loss_start, timestamp))
                current_loss_start = None

            if err is not None and not math.isinf(err):
                errors.append(err)

    # 1. Acquisition Time
    acquisition_time = first_lock_time if first_lock_time is not None else float('inf')
    
    # 2. Tracking Error
    if errors:
        mean_e = sum(errors) / len(errors)
        rmse = math.sqrt(sum(e * e for e in errors) / len(errors))
        max_e = max(errors)
    else:
        mean_e = rmse = max_e = float("nan")

    # 3. Target Loss Rate - frames NOT in LOCKED or COAST (actively tracking)
    tracking_states = {"LOCKED", "COAST", "ACQUIRE"}
    tracking_frames = sum(1 for s in states if s in tracking_states)
    loss_rate_pct = ((total - tracking_frames) / total * 100) if total > 0 else 100.0

    # 4. Re-acquisition Time - mean time from LOST -> LOCKED
    if loss_events:
        reacq_times = [reacq - lost for lost, reacq in loss_events]
        mean_reacq_time = sum(reacq_times) / len(reacq_times)
    else:
        mean_reacq_time = 0.0  # No loss events occurred
    
    # 5. Lock Retention Rate - % of frames in LOCKED after initial acquisition
    lock_retention_pct = (locked_frames_after_first_lock / frames_after_first_lock * 100) \
                         if frames_after_first_lock > 0 else 0.0
    
    # 6. Processing Speed
    if frame_times:
        min_fps = min(frame_times)
        mean_fps = sum(frame_times) / len(frame_times)
    else:
        min_fps = mean_fps = 0.0

    return RunSummary(
        acquisition_time_s=acquisition_time,
        mean_error_px=mean_e,
        max_error_px=max_e,
        rmse_px=rmse,
        target_loss_rate_pct=loss_rate_pct,
        reacquisition_time_s=mean_reacq_time,
        lock_retention_rate_pct=lock_retention_pct,
        min_fps=min_fps,
        mean_fps=mean_fps,
        total_frames=total,
        scenario=scenario,
    )


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "logs/latest.csv"
    name = sys.argv[2] if len(sys.argv) > 2 else "unknown"
    summary = summarise_log(path, scenario=name)
    print(summary.to_markdown())
