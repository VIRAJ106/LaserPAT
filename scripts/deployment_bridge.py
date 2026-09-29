"""
deployment_bridge.py — Unified CLI entry point for LaserPAT.

Maps command-line arguments to either the simulation runner
(scenario_runner) or the headless video-file runner (video_runner).

Usage
-----
Simulation mode (synthetic world):
    python scripts/deployment_bridge.py --mode sim --config configs/sih_benchmark.yaml

Video mode (pre-recorded clip):
    python scripts/deployment_bridge.py --mode video \\
        --video tests/data/sample_30fps.mp4 \\
        --config configs/default.yaml \\
        --output logs/video_out.csv

Stress test (multiple sim runs):
    python scripts/deployment_bridge.py --mode sim \\
        --config configs/clear_linear.yaml \\
        --stress --runs 300

Report generation from existing CSV:
    python scripts/deployment_bridge.py --mode report \\
        --csv logs/run.csv --scenario "SIH Benchmark"
"""

from __future__ import annotations

import argparse
import os
import sys

# Ensure the repo root is on sys.path so "src.*" imports resolve
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def _run_sim(args: argparse.Namespace) -> int:
    """Invoke the simulation scenario runner."""
    from src.modes.scenario_runner import run_scenario  # type: ignore
    from src.logging.report import summarise_log
    import json
    import time

    config = args.config or "configs/default.yaml"

    if args.stress:
        runs = max(1, args.runs)
        print(f"[Bridge] Stress mode: {runs} simulation runs — config: {config}")
        
        # Collect all CSV paths and summaries
        csv_paths = []
        summaries = []
        start_time = time.time()
        
        for i in range(runs):
            print(f"  Run {i + 1}/{runs} …", end=" ", flush=True)
            try:
                csv_path = run_scenario(config, headless=True)
                csv_paths.append(csv_path)
                
                # Analyze the run
                summary = summarise_log(csv_path, scenario=f"StressRun-{i+1}")
                summaries.append(summary)
                
                print(f"PASS RMS={summary.rmse_px:.2f}px FPS={summary.mean_fps:.1f}")
            except Exception as e:
                print(f"FAIL: {e}")
        
        total_time = time.time() - start_time
        
        # Aggregate statistics
        print(f"\n[Bridge] Stress mode complete - {len(summaries)}/{runs} successful runs")
        print(f"  Total time: {total_time:.1f}s ({total_time/runs:.2f}s per run)")
        
        if summaries:
            stats = _aggregate_stress_statistics(summaries, config)
            
            # Save JSON report
            json_output = args.output or f"logs/stress_report_{int(time.time())}.json"
            os.makedirs(os.path.dirname(json_output) or "logs", exist_ok=True)
            
            with open(json_output, 'w') as f:
                json.dump(stats, f, indent=2)
            
            print(f"\n[Bridge] Stress report -> {json_output}")
            _print_stress_summary(stats)
        
    else:
        print(f"[Bridge] Simulation — config: {config}")
        csv_path = run_scenario(config, headless=not args.verbose)
        
        # Generate report if requested
        if not args.verbose:
            from src.logging.report import summarise_log
            summary = summarise_log(csv_path)
            print("\n" + summary.to_markdown())

    return 0


def _aggregate_stress_statistics(summaries, config_name: str) -> dict:
    """
    Aggregate statistics from multiple stress runs.
    
    Returns JSON-serializable dict with mean, p95, worst-case metrics.
    """
    import numpy as np
    
    # Extract metrics arrays
    acquisition_times = [s.acquisition_time_s for s in summaries if not np.isinf(s.acquisition_time_s)]
    rmse_values = [s.rmse_px for s in summaries if not np.isnan(s.rmse_px)]
    mean_errors = [s.mean_error_px for s in summaries if not np.isnan(s.mean_error_px)]
    max_errors = [s.max_error_px for s in summaries if not np.isnan(s.max_error_px)]
    loss_rates = [s.target_loss_rate_pct for s in summaries]
    reacq_times = [s.reacquisition_time_s for s in summaries]
    lock_retention = [s.lock_retention_rate_pct for s in summaries]
    min_fps_values = [s.min_fps for s in summaries]
    mean_fps_values = [s.mean_fps for s in summaries]
    
    def stats_dict(values, label):
        if not values:
            return {"mean": None, "p95": None, "worst": None, "best": None}
        arr = np.array(values)
        return {
            "label": label,
            "mean": float(np.mean(arr)),
            "median": float(np.median(arr)),
            "p95": float(np.percentile(arr, 95)),
            "worst": float(np.max(arr)) if "error" in label.lower() or "loss" in label.lower() else float(np.min(arr)),
            "best": float(np.min(arr)) if "error" in label.lower() or "loss" in label.lower() else float(np.max(arr)),
            "std": float(np.std(arr)),
        }
    
    return {
        "config": config_name,
        "total_runs": len(summaries),
        "successful_runs": len(summaries),
        "metrics": {
            "acquisition_time_s": stats_dict(acquisition_times, "Acquisition Time (s)"),
            "rmse_px": stats_dict(rmse_values, "RMS Error (px)"),
            "mean_error_px": stats_dict(mean_errors, "Mean Error (px)"),
            "max_error_px": stats_dict(max_errors, "Max Error (px)"),
            "target_loss_rate_pct": stats_dict(loss_rates, "Target Loss Rate (%)"),
            "reacquisition_time_s": stats_dict(reacq_times, "Re-acquisition Time (s)"),
            "lock_retention_rate_pct": stats_dict(lock_retention, "Lock Retention (%)"),
            "min_fps": stats_dict(min_fps_values, "Min FPS"),
            "mean_fps": stats_dict(mean_fps_values, "Mean FPS"),
        }
    }


def _print_stress_summary(stats: dict) -> None:
    """Print human-readable stress test summary."""
    print("\n" + "="*70)
    print("STRESS GATE SUMMARY")
    print("="*70)
    print(f"Config: {stats['config']}")
    print(f"Runs: {stats['successful_runs']}/{stats['total_runs']}")
    print("\nAggregate Statistics (Mean / p95 / Worst):")
    print("-"*70)
    
    metrics = stats['metrics']
    
    print(f"  Acquisition Time:   {metrics['acquisition_time_s']['mean']:.3f}s / "
          f"{metrics['acquisition_time_s']['p95']:.3f}s / "
          f"{metrics['acquisition_time_s']['worst']:.3f}s")
    
    print(f"  RMS Error:          {metrics['rmse_px']['mean']:.2f}px / "
          f"{metrics['rmse_px']['p95']:.2f}px / "
          f"{metrics['rmse_px']['worst']:.2f}px")
    
    print(f"  Mean Error:         {metrics['mean_error_px']['mean']:.2f}px / "
          f"{metrics['mean_error_px']['p95']:.2f}px / "
          f"{metrics['mean_error_px']['worst']:.2f}px")
    
    print(f"  Target Loss Rate:   {metrics['target_loss_rate_pct']['mean']:.1f}% / "
          f"{metrics['target_loss_rate_pct']['p95']:.1f}% / "
          f"{metrics['target_loss_rate_pct']['worst']:.1f}%")
    
    print(f"  Re-acquisition:     {metrics['reacquisition_time_s']['mean']:.3f}s / "
          f"{metrics['reacquisition_time_s']['p95']:.3f}s / "
          f"{metrics['reacquisition_time_s']['worst']:.3f}s")
    
    print(f"  Min FPS:            {metrics['min_fps']['mean']:.1f} / "
          f"{metrics['min_fps']['p95']:.1f} / "
          f"{metrics['min_fps']['worst']:.1f}")
    
    print(f"  Mean FPS:           {metrics['mean_fps']['mean']:.1f} / "
          f"{metrics['mean_fps']['p95']:.1f} / "
          f"{metrics['mean_fps']['worst']:.1f}")
    
    print("\n" + "="*70)
    
    # Gate status
    gate_pass = True
    gate_failures = []
    
    if metrics['rmse_px']['p95'] > 10.0:
        gate_pass = False
        gate_failures.append(f"RMS Error p95 {metrics['rmse_px']['p95']:.2f}px > 10px")
    
    if metrics['target_loss_rate_pct']['p95'] >= 5.0:
        gate_pass = False
        gate_failures.append(f"Loss Rate p95 {metrics['target_loss_rate_pct']['p95']:.1f}% >= 5%")
    
    if metrics['min_fps']['worst'] < 20.0:
        gate_pass = False
        gate_failures.append(f"Min FPS worst {metrics['min_fps']['worst']:.1f} < 20")
    
    if gate_pass:
        print("✅ STRESS GATE: PASSED")
    else:
        print("❌ STRESS GATE: FAILED")
        for failure in gate_failures:
            print(f"   - {failure}")
    
    print("="*70 + "\n")


def _run_video(args: argparse.Namespace) -> int:
    """Invoke the headless video runner."""
    from src.modes.video_runner import run_video  # type: ignore

    if not args.video:
        print("[Bridge] ERROR: --video is required in video mode.", file=sys.stderr)
        return 1

    config = args.config or "configs/default.yaml"
    output = args.output  # may be None — video_runner will auto-generate

    print(f"[Bridge] Video mode — video: {args.video}  config: {config}")
    csv_path = run_video(
        video_path=args.video,
        config_path=config,
        output_csv=output,
        verbose=not args.quiet,
    )
    print(f"[Bridge] CSV written -> {csv_path}")

    if args.report:
        _generate_report(csv_path, scenario=os.path.basename(args.video))

    return 0


def _run_report(args: argparse.Namespace) -> int:
    """Generate a Markdown report from an existing CSV log."""
    from src.logging.report import summarise_log  # type: ignore

    if not args.csv:
        print("[Bridge] ERROR: --csv is required in report mode.", file=sys.stderr)
        return 1

    scenario = args.scenario or os.path.basename(args.csv)
    _generate_report(args.csv, scenario=scenario)
    return 0


def _generate_report(csv_path: str, scenario: str = "unknown") -> None:
    from src.logging.report import summarise_log  # type: ignore

    summary = summarise_log(csv_path, scenario=scenario)
    md = summary.to_markdown()
    print("\n" + md + "\n")

    # Optionally write alongside the CSV
    report_path = csv_path.replace(".csv", "_report.md")
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(md + "\n")
        print(f"[Bridge] Report saved -> {report_path}")
    except OSError as exc:
        print(f"[Bridge] Warning: could not write report file - {exc}")


def _run_export(args: argparse.Namespace) -> int:
    """Export PID gains and KF matrices as a C header."""
    from src.config import load_config
    config = args.config or "configs/default.yaml"
    cfg = load_config(config)
    output = args.output or "laserpat_config.h"

    # KF matrices (Constant Velocity)
    dt = 1.0 / 30.0
    q = 1.0
    r = 5.0

    header = f"""#ifndef LASERPAT_CONFIG_H
#define LASERPAT_CONFIG_H

// Auto-generated from {config}

// PID Gains
#define PID_KP {cfg.control.kp}f
#define PID_KI {cfg.control.ki}f
#define PID_KD {cfg.control.kd}f

// Kalman Filter Matrices
#define KF_DT {dt}f
#define KF_Q_NOISE {q}f
#define KF_R_NOISE {r}f

// PAT Supervisor State Machine
#define PAT_LOCK_THRESHOLD_PX {cfg.estimation.lock_threshold_px}f
#define PAT_REQUIRED_LOCK_FRAMES {cfg.estimation.lock_frames}

#endif // LASERPAT_CONFIG_H
"""
    try:
        with open(output, "w") as f:
            f.write(header)
        print(f"[Bridge] C-struct header written -> {output}")
    except OSError as exc:
        print(f"[Bridge] ERROR writing C-struct header: {exc}", file=sys.stderr)
        return 1
    return 0



# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="deployment_bridge",
        description="LaserPAT deployment bridge — sim, video, or report modes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    p.add_argument(
        "--mode",
        choices=["sim", "video", "report", "export-c"],
        default="sim",
        help="Execution mode: 'sim' (default), 'video', 'report', or 'export-c'",
    )

    # Shared
    p.add_argument(
        "--config",
        default=None,
        help="Path to YAML config (default: configs/default.yaml)",
    )
    p.add_argument(
        "--output",
        default=None,
        help="Output CSV file path (video mode; auto-generated if omitted)",
    )
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print frame-level progress (sim mode)",
    )
    p.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress progress output (video mode)",
    )

    # Sim-mode options
    p.add_argument(
        "--stress",
        action="store_true",
        help="Run multiple simulation passes (sim mode)",
    )
    p.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of stress runs (requires --stress, default: 1)",
    )

    # Video-mode options
    p.add_argument(
        "--video",
        default=None,
        help="Input video file (.mp4 / .avi) — required in video mode",
    )
    p.add_argument(
        "--report",
        action="store_true",
        help="Auto-generate a Markdown report after video processing",
    )

    # Report-mode options
    p.add_argument(
        "--csv",
        default=None,
        help="Existing CSV log file to summarise (report mode)",
    )
    p.add_argument(
        "--scenario",
        default=None,
        help="Scenario name label for the report (report mode)",
    )

    return p


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    dispatch = {
        "sim": _run_sim,
        "video": _run_video,
        "report": _run_report,
        "export-c": _run_export,
    }

    handler = dispatch.get(args.mode)
    if handler is None:
        parser.print_help()
        return 1

    try:
        return handler(args)
    except KeyboardInterrupt:
        print("\n[Bridge] Interrupted by user.")
        return 130
    except Exception as exc:
        print(f"[Bridge] FATAL: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
