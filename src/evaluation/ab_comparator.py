"""
ab_comparator.py — A/B comparison tool for two simulation runs.

Reads two CSV logs produced by CSVLogger and generates a side-by-side
Markdown comparison table.  Used to evaluate the impact of enabling/disabling
the AI Verifier, changing weather conditions, or tuning PID gains.
"""
import csv
import math
import sys
from typing import Dict, List


def _load_errors(path: str) -> List[float]:
    errors: List[float] = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                e = float(row.get("tracking_error_px", "inf"))
                if not math.isinf(e):
                    errors.append(e)
            except (ValueError, TypeError):
                pass
    return errors


def _load_lock_rate(path: str) -> float:
    total = lock = 0
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            if row.get("state", "") == "LOCKED":
                lock += 1
    return (lock / total * 100) if total > 0 else 0.0


def _stats(errors: List[float]) -> Dict[str, float]:
    if not errors:
        return {"mean": float("nan"), "rmse": float("nan"), "max": float("nan")}
    mean = sum(errors) / len(errors)
    rmse = math.sqrt(sum(e * e for e in errors) / len(errors))
    return {"mean": mean, "rmse": rmse, "max": max(errors)}


def compare_runs(path_a: str, path_b: str, label_a: str = "Run A", label_b: str = "Run B") -> str:
    err_a, err_b = _load_errors(path_a), _load_errors(path_b)
    lock_a, lock_b = _load_lock_rate(path_a), _load_lock_rate(path_b)
    st_a, st_b = _stats(err_a), _stats(err_b)

    lines = [
        f"## A/B Comparison: `{label_a}` vs `{label_b}`",
        "",
        f"| Metric | {label_a} | {label_b} | Δ |",
        f"|--------|-----------|-----------|---|",
        f"| Lock Rate (%) | {lock_a:.1f} | {lock_b:.1f} | {lock_b - lock_a:+.1f} |",
        f"| Mean Error (px) | {st_a['mean']:.2f} | {st_b['mean']:.2f} | {st_b['mean'] - st_a['mean']:+.2f} |",
        f"| RMSE (px) | {st_a['rmse']:.2f} | {st_b['rmse']:.2f} | {st_b['rmse'] - st_a['rmse']:+.2f} |",
        f"| Max Error (px) | {st_a['max']:.2f} | {st_b['max']:.2f} | {st_b['max'] - st_a['max']:+.2f} |",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python -m src.evaluation.ab_comparator <run_a.csv> <run_b.csv> [label_a] [label_b]")
        sys.exit(1)
    la = sys.argv[3] if len(sys.argv) > 3 else "Run A"
    lb = sys.argv[4] if len(sys.argv) > 4 else "Run B"
    print(compare_runs(sys.argv[1], sys.argv[2], la, lb))
