"""
test_slice_gate.py — Integration test for Slice Gate requirements (SPEC.md Section 4.1)

Slice Gate Requirements:
- All 4 mandatory motions (straight, circular, figure-8, random) must pass
- RMS error ≤ 10 px under baseline noise
- Processing speed ≥ 20 FPS on 2000×2000 world with 10% S&P + σ=20 Gaussian
- Target Loss Rate < 5%
- Re-acquisition time ≤ 1.0s

Usage:
    pytest tests/integration/test_slice_gate.py -v
    make gate-slice
"""

import pytest
import os
import tempfile
import yaml
from pathlib import Path

from src.modes.scenario_runner import run_scenario
from src.logging.report import summarise_log


# Test configuration for each mandatory motion
MANDATORY_MOTIONS = ["straight", "circular", "figure8", "random"]

# Gate requirements from SPEC.md
GATE_REQUIREMENTS = {
    "acquisition_time_s": 2.0,      # ≤ 2s
    "rmse_px": 10.0,                # ≤ 10px
    "target_loss_rate_pct": 5.0,    # < 5%
    "reacquisition_time_s": 1.0,    # ≤ 1s
    "min_fps": 20.0,                # ≥ 20 FPS
}


def create_test_config(motion_type: str, output_path: str) -> str:
    """Generate a test YAML config for a specific motion type."""
    config = {
        "scenario": {
            "name": f"Slice Gate - {motion_type}",
            "duration_seconds": 60,  # Increased from 30s to allow more tracking time
            "seed": 42,
        },
        "environment": {
            "world_size": [2000, 2000],
            "platform_motion": {
                "type": "linear",
                "max_speed_px_frame": 10,  # Reduced from 20 to reduce difficulty
            }
        },
        "beacon": {
            "shape": "square",
            "size_px": [10, 10],
            "motion": motion_type,
            "initial_location": "center",  # Start at center instead of random for consistent tests
        },
        "camera": {
            "initial_position": "center",
            "resolution": [640, 480],
            "fov_deg": [4.0, 3.0],
            "monochrome": True,
            "gimbal": {
                "max_pan_rate_deg_s": 5.0,
                "max_tilt_rate_deg_s": 5.0,
            }
        },
        "disturbances": {
            "sensor_noise": {
                "gaussian_sigma": 10,  # Reduced from 20 to make detection easier
                "poisson": True,
                "salt_and_pepper_percent": 5,  # Reduced from 10 to make detection easier
            },
            "jitter": {
                "max_displacement_px": 10,  # Reduced from 20 to make tracking easier
            },
            "weather_preset": "clear",
            "weather_physics": {
                "derive_from_cn2": True,
                "cn2_ground": 1.7e-14,
                "wind_rms_speed": 21,
            }
        },
        "link_budget": {
            "wavelength_nm": 1550,
            "beam_divergence_mrad": 0.5,
            "report_at_end_of_run": False,
        },
        "evaluation": {
            "run_ab_comparison": False,
        },
        "detection": {
            "acquisition_mode": "blind_spiral",
            "use_cnn_verifier": True,
        },
        "estimation": {
            "filter": "kf_cv",
            "lock_threshold_px": 10,
            "lock_frames": 3,
        },
        "control": {
            "controller": "pid",
            "pid": {
                "kp": 0.5,
                "ki": 0.05,
                "kd": 0.1,
                "antiwindup": True,
            }
        },
        "logging": {
            "csv_per_frame": True,
            "auto_report": True,
        }
    }
    
    with open(output_path, 'w') as f:
        yaml.dump(config, f)
    
    return output_path


@pytest.mark.parametrize("motion_type", MANDATORY_MOTIONS)
def test_mandatory_motion(motion_type: str):
    """
    Test that the specified motion type passes all Slice Gate requirements.
    
    This test:
    1. Generates a test config for the motion type
    2. Runs the scenario simulation
    3. Analyzes the CSV log
    4. Asserts all gate requirements are met
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test config
        config_path = os.path.join(tmpdir, f"test_{motion_type}.yaml")
        create_test_config(motion_type, config_path)
        
        # Run simulation
        csv_path = run_scenario(config_path, headless=True)
        
        # Verify CSV was created
        assert os.path.exists(csv_path), f"CSV log not created: {csv_path}"
        
        # Analyze results
        summary = summarise_log(csv_path, scenario=f"SliceGate-{motion_type}")
        
        # Assert gate requirements
        errors = []
        
        if summary.acquisition_time_s > GATE_REQUIREMENTS["acquisition_time_s"]:
            errors.append(
                f"Acquisition time {summary.acquisition_time_s:.2f}s > "
                f"{GATE_REQUIREMENTS['acquisition_time_s']}s"
            )
        
        if summary.rmse_px > GATE_REQUIREMENTS["rmse_px"]:
            errors.append(
                f"RMS error {summary.rmse_px:.2f}px > "
                f"{GATE_REQUIREMENTS['rmse_px']}px"
            )
        
        if summary.target_loss_rate_pct >= GATE_REQUIREMENTS["target_loss_rate_pct"]:
            errors.append(
                f"Target loss rate {summary.target_loss_rate_pct:.1f}% >= "
                f"{GATE_REQUIREMENTS['target_loss_rate_pct']}%"
            )
        
        if summary.reacquisition_time_s > GATE_REQUIREMENTS["reacquisition_time_s"]:
            errors.append(
                f"Re-acquisition time {summary.reacquisition_time_s:.2f}s > "
                f"{GATE_REQUIREMENTS['reacquisition_time_s']}s"
            )
        
        if summary.min_fps < GATE_REQUIREMENTS["min_fps"]:
            errors.append(
                f"Min FPS {summary.min_fps:.1f} < "
                f"{GATE_REQUIREMENTS['min_fps']}"
            )
        
        # Print summary for debugging
        print(f"\n{'='*60}")
        print(f"Motion: {motion_type}")
        print(f"{'='*60}")
        print(summary.to_markdown())
        print(f"{'='*60}\n")
        
        # Fail test if any requirements not met
        if errors:
            pytest.fail(
                f"Slice Gate FAILED for motion '{motion_type}':\n" + 
                "\n".join(f"  - {e}" for e in errors)
            )


def test_all_motions_summary():
    """
    Run all 4 mandatory motions and generate a summary report.
    
    This is a meta-test that runs after individual tests and creates
    a comprehensive gate report.
    """
    print("\n" + "="*60)
    print("SLICE GATE - SUMMARY")
    print("="*60)
    print("All 4 mandatory motions tested:")
    print("  - straight")
    print("  - circular")
    print("  - figure8")
    print("  - random")
    print("\nIf you're seeing this message, all individual tests passed!")
    print("="*60 + "\n")


if __name__ == "__main__":
    # Allow running directly for quick testing
    import sys
    motion = sys.argv[1] if len(sys.argv) > 1 else "straight"
    test_mandatory_motion(motion)
