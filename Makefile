# =============================================================================
# LaserPAT — Makefile
# =============================================================================
# Targets
#   setup        Install package + dev dependencies
#   test         Run full pytest suite
#   run          Launch GUI desktop app
#   run-headless Run simulation headlessly (clear_linear scenario)
#   train        Generate synthetic patches and train patch-verifier CNN
#   bench        Run the official SIH benchmark via deployment_bridge
#   package      Build distributable .exe with PyInstaller (onedir)
#   clean        Remove build artefacts
#   gate-slice   Integration gate: slice test
#   gate-benchmark Gate: headless video benchmark
#   gate-stress  Gate: 300-run stress pass
# =============================================================================

.PHONY: setup test run run-headless train bench package clean \
        gate-slice gate-benchmark gate-stress

# ---------------------------------------------------------------------------
# Environment / paths
# ---------------------------------------------------------------------------
PYTHON      ?= python
CONFIG_SIM  ?= configs/sih_benchmark.yaml
CONFIG_BENCH?= configs/sih_benchmark.yaml
VIDEO_BENCH ?= tests/data/sample_30fps.mp4

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
setup:
	$(PYTHON) -m pip install -e .[dev]

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
test:
	$(PYTHON) -m pytest tests/ -v

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
run:
	$(PYTHON) main.py

run-headless:
	$(PYTHON) scripts/deployment_bridge.py --mode sim --config configs/clear_linear.yaml

# ---------------------------------------------------------------------------
# Train  — generate synthetic patches, then train + export to ONNX
# ---------------------------------------------------------------------------
train:
	@echo ">>> Generating synthetic training patches..."
	$(PYTHON) models/scripts/generate_synthetic_patches.py
	@echo ">>> Training TinyPatchCNN and exporting to ONNX..."
	$(PYTHON) models/scripts/train_patch_cnn.py
	@echo ">>> Model written to models/patch_verifier_cnn.onnx"

# ---------------------------------------------------------------------------
# Bench  — run SIH benchmark scenario, generate report
# ---------------------------------------------------------------------------
bench:
	@echo ">>> Running SIH benchmark ($(CONFIG_BENCH))..."
	$(PYTHON) scripts/deployment_bridge.py --mode sim \
	    --config $(CONFIG_BENCH) \
	    --verbose
	@echo ">>> Benchmark complete."

# ---------------------------------------------------------------------------
# Package  — build standalone Windows EXE with PyInstaller
# ---------------------------------------------------------------------------
package:
	@echo ">>> Building LaserPAT distributable (onedir)..."
	$(PYTHON) -m PyInstaller --noconfirm laserpat.spec
	@echo ">>> Executable ready in dist/LaserPAT/"

# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------
clean:
	$(PYTHON) -c "import shutil, glob; \
	    [shutil.rmtree(p, ignore_errors=True) for p in \
	        ['build', 'dist', '.pytest_cache', 'src/laserpat.egg-info'] + \
	        glob.glob('**/__pycache__', recursive=True)]"
	@echo ">>> Clean done."

# ---------------------------------------------------------------------------
# Gate tests (CI / demo-day checks)
# ---------------------------------------------------------------------------
gate-slice:
	$(PYTHON) -m pytest tests/integration/test_slice_gate.py -v

gate-benchmark:
	$(PYTHON) scripts/deployment_bridge.py --mode video \
	    --video $(VIDEO_BENCH) \
	    --config configs/default.yaml \
	    --report
	@echo ">>> gate-benchmark: check logs/ for CSV + _report.md"

gate-stress:
	$(PYTHON) scripts/deployment_bridge.py --mode sim \
	    --config configs/clear_linear.yaml \
	    --stress --runs 300
	@echo ">>> gate-stress complete (300 runs)."
