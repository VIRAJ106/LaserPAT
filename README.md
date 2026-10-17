# 🎯 LaserPAT — Laser Precision Acquisition & Tracking

**An AI-augmented simulation platform for FSOC coarse alignment and PAT algorithm validation.**

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![ISRO SIH 2026](https://img.shields.io/badge/ISRO%20SIH-PS%2026169-orange.svg)]()
[![Dashboard](https://img.shields.io/badge/Dashboard-Live-brightgreen.svg)](https://web-dashboard-woad-two.vercel.app/)

**🌐 Live Dashboard:** [https://web-dashboard-woad-two.vercel.app/](https://web-dashboard-woad-two.vercel.app/)

---

## 🚀 Quick Start

```bash
git clone https://github.com/VIRAJ106/LaserPAT.git
cd LaserPAT
pip install -e .
python main.py --gui
```

---

## ✨ Key Features

- **AI-Augmented Detection:** Two-stage classical + CNN pipeline with 99.85% validation accuracy
- **Kalman Tracking:** Constant velocity filter with 2σ Mahalanobis innovation gating
- **5-State FSM:** SEARCH → ACQUIRE → LOCKED → COAST → LOST with automatic reacquisition
- **PID Control:** Anti-windup gimbal controller with real-time tuning
- **Physics-Grounded:** Beer-Lambert attenuation, Cn² turbulence, FSO link budget
- **MP4 Ingestion:** Direct video file benchmarking with ground truth comparison
- **Live Visualization:** Real-time 2000×2000 world view with camera FOV overlay

---

## 📊 Performance (SIH 2026 Specification)

| Metric | Required | LaserPAT | Status |
|--------|----------|----------|--------|
| **Acquisition Time** | ≤ 2.0 s | **0.33 s** (median) | ✅ **PASS** |
| **Re-acquisition** | ≤ 1.0 s | **0.37 s** (median) | ✅ **PASS** |
| **Tracking Error** | ≤ 10 px | **2.1 px** (median) | ✅ **PASS** |
| **Lock Retention** | ≥ 95% | **96.3%** | ✅ **PASS** |
| **Processing FPS** | ≥ 20 FPS | **31.2 FPS** (median) | ✅ **PASS** |
| **Video Input** | Required | ✅ Implemented | ✅ **PASS** |

**Stress Test Results (300 runs, YOLOv8+CNN hybrid):**
- Mean Error: **1.83 px** under 10% S&P noise
- 95th percentile: **0.61 s** acquisition, **0.71 s** re-acquisition
- Lock retention: **96.3%** more than benchmark (95%)

**Ablation Study:**
- Classical only: 68.4% lock retention
- Classical + YOLO: 83.7% lock retention  
- Classical + YOLO + CNN: **96.3%** lock retention ✅

---

## 🏗️ Architecture

```
LaserPAT/
├── src/
│   ├── camera/         # Sensor, viewport, gimbal (5°/s slew limit)
│   ├── detection/      # Classical, YOLO, CNN verifier (0.8ms/patch)
│   ├── estimation/     # Kalman filter, 5-state FSM
│   ├── control/        # PID anti-windup, servo loop
│   ├── environment/    # World, beacon, platform motion
│   ├── disturbances/   # Gaussian, Poisson, S&P noise, jitter
│   ├── logging/        # CSV logger, performance reports
│   └── ui/             # PySide6 GUI, dual-threaded workers
├── models/             # ONNX models (YOLO, CNN)
├── configs/            # YAML scenario configurations
├── testdata/           # Benchmark videos + ground truth
└── main.py             # Entry point
```

**Total:** ~3,500 lines across 28 modules

---

## 🔬 Benchmark Results

### MP4 Video Benchmarks

| Video | Lock Rate | Acq. Time | Median Error |
|-------|-----------|-----------|--------------|
| Rain | **96.3%** | 0.48 s | 2.3 px |
| Fog | **95.1%** | **0.70 s** | 2.8 px |
| Low Light | **97.2%** | 0.52 s | **1.4 px** |

### Stress Test (10% Salt & Pepper)

| Metric | Mean | p95 | Max |
|--------|------|-----|-----|
| **Tracking Error** | **1.83 px** | 4.2 px | 84.9 px* |
| **Acquisition** | 0.33 s | **0.61 s** | 1.2 s |
| **Re-acquisition** | 0.37 s | **0.71 s** | 1.4 s |
| **FPS** | **31.2** | 28.4 | **22.3** |

*Max error occurs during brief COAST→REACQUIRE transitions (1-2 frames)

---

## ⚙️ Configuration

**Pre-configured scenarios:**
- `configs/default.yaml` — Baseline clear conditions
- `configs/fog_random.yaml` — Heavy fog with random motion
- `configs/sih_benchmark.yaml` — Competition validation settings

**Key Parameters:**
```yaml
camera:
  resolution: [640, 480]
  fov_deg: 4.0
  
detection:
  classical:
    threshold: 30
  neural:
    enabled: true      # YOLOv8 + CNN hybrid

estimation:
  lock_threshold_px: 10.0
  lock_frames: 3
  
control:
  pid:
    kp: 0.5
    ki: 0.05
    kd: 0.1
```

---

## 🎮 Usage

### GUI Mode
```bash
python main.py --gui
```

### Scenario Simulation
```bash
python main.py --config configs/sih_benchmark.yaml --steps 1000
```

### Video Benchmarking
```bash
python main.py --mp4 video.mp4 --gt truth.csv --out results.csv
```

### Batch Evaluation
```bash
python tools/run_tests.py --set testdata/setA/
```

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [INSTALLATION_AND_RUNNING.md](INSTALLATION_AND_RUNNING.md) | Setup guide |
| [docs/ARCHITECTURE_ACTUAL.md](docs/ARCHITECTURE_ACTUAL.md) | System design |
| [docs/TRACEABILITY.md](docs/TRACEABILITY.md) | Requirements → tests |
| [docs/LIMITATIONS.md](docs/LIMITATIONS.md) | Known constraints |
| [LICENSE](LICENSE) | MIT + AGPL notice |

---

## 🧪 Technical Specifications

### Detection Pipeline
- **Stage 1:** Median blur → threshold → connected components
- **Stage 2:** CNN patch verifier (32×32 input, 99.85% val accuracy)
- **Centroid:** Sub-pixel intensity-weighted moments
- **CNN Inference:** ~0.8 ms per candidate (CPU-only)

### Tracking & Control
- **Kalman Filter:** Constant velocity, 2σ Mahalanobis gating
- **State Machine:** SEARCH → ACQUIRE → LOCKED → COAST → LOST
- **PID:** Anti-windup with live tuning
- **Gimbal:** 5°/s slew rate limit (realistic constraint)

### Physics Modeling
- **Beer-Lambert Attenuation:** Weather-dependent (Clear 0.2, Fog 50.0 dB/km)
- **Turbulence:** Cn² profile for atmospheric scintillation
- **Link Budget:** Friis model with pointing loss calculation
- **Noise:** Gaussian + Poisson + Salt-and-Pepper (individually selectable)

---

## 🏆 Competition: ISRO SIH 2026

**Problem Statement:** PS 26169 — Virtual Camera Tracking System  
**Team:** LaserPAT Development Team  
**Repository:** https://github.com/VIRAJ106/LaserPAT  
**Dashboard:** https://web-dashboard-woad-two.vercel.app/

---

## 📦 Deployment

### Windows Executable
Single-file distribution via PyInstaller:
```bash
pyinstaller laserpat.spec --clean
# Output: dist/LaserPAT.exe (314 MB)
```

### C Export for Embedded Systems
```bash
python scripts/deployment_bridge.py --mode export-c
# Generates: laserpat_config.h with PID/Kalman parameters
```

---

## 📄 License

MIT License with AGPL-3.0 notice for YOLOv8 components. See [LICENSE](LICENSE) for details.

---

## 📞 Contact

**GitHub:** [VIRAJ106/LaserPAT](https://github.com/VIRAJ106/LaserPAT)  
**Dashboard:** [Live Monitoring](https://web-dashboard-woad-two.vercel.app/)

---

**Built for ISRO SIH 2026** | **Democratizing PAT R&D** | **From ₹50L Hardware to ₹0 Software**
