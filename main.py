import sys
import os
import argparse

# Ensure the repo root is on sys.path so src.* imports resolve correctly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ui.app import launch_dashboard


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LaserPAT — FSOC Coarse Alignment Simulator")
    parser.add_argument(
        "--config",
        type=str,
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "configs", "sih_benchmark.yaml"),
        help="Path to scenario YAML config (default: configs/sih_benchmark.yaml)"
    )
    args = parser.parse_args()
    launch_dashboard(args.config)
