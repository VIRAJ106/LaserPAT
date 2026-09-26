# LaserPAT — Formal Specifications and Definitions

This document serves as the official source of truth for the definition of all tracking metrics, states, and performance constraints evaluated in LaserPAT. It is directly mapped to the SIH26169 problem statement.

## 1. Tracking State Machine

The system transitions between the following states:
- `IDLE`: System is initialized but not yet active.
- `SEARCH`: Actively sweeping the Field of Uncertainty using a scan pattern (e.g., spiral).
- `ACQUIRE`: A candidate has been detected. The system evaluates the candidate over multiple frames.
- `LOCKED`: The tracking error has been ≤ threshold for N consecutive frames. 
- `COAST`: The target is temporarily lost (e.g., cloud cover or noise spike). The estimator continues predicting the target position without measurement updates.
- `LOST`: Coast timeout exceeded or uncertainty covariance exceeds the Region of Interest (ROI) bounds. System will attempt to reacquire or fallback to `SEARCH`.
- `REACQUIRE`: Valid detection found within the expanded ROI while in the `LOST` or `COAST` state.

## 2. Core Metrics Definition

To ensure rigorous evaluation, all tracking and performance metrics are defined as follows:

### 2.1 Tracking Error (Centroiding Error)
- **Diagnostic Logging**: The system logs the per-axis error (Δx, Δy) where Δx = detected_x - truth_x, and Δy = detected_y - truth_y.
- **Canonical Definition**: The tracking error used for gating and reporting is the **Euclidean distance**: 
  `error = √(Δx² + Δy²)`
- **Constraint**: The Problem Statement's requirement of "≤ 10 pixels" is a scalar magnitude bound. The system evaluates `error ≤ 10` for lock and performance metrics, never Δx or Δy individually.

### 2.2 Temporal Metrics
- **Acquisition Time**: The total time elapsed from the start of the `SEARCH` state to the first frame where the state transitions to `LOCKED`.
- **Lock**: Achieved when the Euclidean tracking error is ≤ the lock threshold (default 10px) for a consecutive number of frames (default N=3).
- **Lock Retention Rate**: The percentage of frames spent in the `LOCKED` state, calculated from the moment of initial lock until the end of the scenario.
- **Target Loss Rate**: The percentage of frames across the entire run where the system is not actively tracking the target (i.e., not in `LOCKED` or `COAST` with valid prediction).
- **Re-acquisition Time**: The time elapsed from entering the `LOST` state to returning to the `LOCKED` state.

## 3. Benchmark Outputs

Every scenario and video-mode run must emit the following metrics into a CSV log and auto-generated report:
1. **Acquisition Time (s)**
2. **Tracking Error**: Mean, Maximum, and RMS (Root Mean Square) as Euclidean distance (px).
3. **Target Loss Rate** (%)
4. **Re-acquisition Time (s)** (per loss event, summarized as mean/max)
5. **Lock Retention Rate** (%)
6. **Processing Speed (FPS)**: Minimum and Mean.

## 4. Performance Gates

### 4.1 Slice Gate
- **Motions**: Must pass on straight, circular, figure-8, and random walk.
- **Error**: RMS error ≤ 10 px under baseline noise.
- **Speed**: ≥ 20 FPS processing speed on a 2000x2000 world with 10% S&P + σ=20 Gaussian noise.
- **Losses**: Target Loss Rate < 5%.
- **Re-acquisition**: Re-acquisition time ≤ 1.0s.

### 4.2 Benchmark Gate
- **MP4 Video Mode**: Successfully ingests a 30fps file and outputs compliant CSV logs.
- **Reporting**: Automated JSON/HTML report generation completes at the end of a run.

### 4.3 Stress Gate
- **Monte Carlo**: N ≥ 300 seeded runs per mandatory motion type at maximum noise/jitter settings.
- **Reporting**: Generates the statistically significant Mean, p95, and Worst-Case Tracking Error and FPS for the final technical report.
