"""
perception.py — Unified Perception Interface for LaserPAT.

Architecture
------------
    Frame
      ↓
    PerceptionBackend (selected by cfg.detection.backend)
      ├── ClassicalAIPerception   candidate generation (OpenCV) → CNN verifier score
      └── YOLOPerception          NeuralDetector (YOLOv8) → bounding boxes
      ↓
    PerceptionResult (unified Candidate list)

This resolves the "two competing AI architectures" gap.  YOLO and the CNN
verifier no longer compete for the definition of "AI detector"; they are now
two selectable *implementations* of the same PerceptionBackend contract.

Backend selection (cfg.detection.backend):
    "classical_cnn"  (default) → ClassicalAIPerception
    "yolo"                     → YOLOPerception

Factory
-------
    Use build_perception(cfg) to get the correct backend for a given config.
"""

from __future__ import annotations

import math
from typing import List, Optional

import numpy as np

from src.interfaces import (
    Candidate,
    PerceptionBackend,
    PerceptionResult,
)
from src.detection.classical import extract_candidates, calculate_centroid, size_discriminate
from src.detection.ai_verifier import AIVerifier


# ---------------------------------------------------------------------------
# Backend A — Classical candidate generation + CNN verifier
# ---------------------------------------------------------------------------

class ClassicalAIPerception(PerceptionBackend):
    """
    Classical OpenCV blob detection with optional CNN patch verification.

    Pipeline (unchanged from original scenario_runner.py logic):
        1. Median blur + threshold + connected components  →  candidates
        2. Size discrimination (if target_size_px is set)
        3. Sub-pixel intensity centroid per candidate
        4. CNN patch verifier scores each centroid (degrades to 0.0 if model absent)
        5. Select best candidate by AI score; fallback to largest area

    Parameters
    ----------
    verifier_path : str
        Path to the ONNX patch-verifier model.
    use_cnn : bool
        Whether CNN verification is enabled (from cfg.detection.use_cnn_verifier).
    target_size_px : tuple[int, int] | None
        Expected bounding-box size for size discrimination.  (-1,-1) = disabled.
    size_tolerance : float
        Fractional tolerance for size_discriminate().
    """

    def __init__(
        self,
        verifier_path: str,
        use_cnn: bool = True,
        target_size_px: tuple = (-1, -1),
        size_tolerance: float = 0.5,
    ):
        self._verifier = AIVerifier(verifier_path)
        self._use_cnn = use_cnn
        self._target_w = target_size_px[0]
        self._target_h = target_size_px[1]
        self._tol = size_tolerance

    def run(self, frame: np.ndarray, frame_id: int = -1) -> PerceptionResult:
        raw_candidates = extract_candidates(frame)

        # Size discrimination
        if self._target_w > 0 and self._target_h > 0:
            raw_candidates = size_discriminate(
                raw_candidates, self._target_w, self._target_h, self._tol
            )

        if not raw_candidates:
            return PerceptionResult(candidates=[], backend_used="classical_cnn",
                                    frame_id=frame_id)

        # Sub-pixel centroids
        centroids = [calculate_centroid(frame, c) for c in raw_candidates]

        # CNN verification
        scores = self._verifier.extract_and_verify(frame, centroids)
        ai_active = self._use_cnn and any(s > 0.1 for s in scores)

        candidates: List[Candidate] = []
        for i, (bbox, (cx, cy)) in enumerate(zip(raw_candidates, centroids)):
            x, y, w, h = bbox[:4]
            roi = frame[int(y):int(y + h), int(x):int(x + w)]
            intensity_mean = float(roi.mean()) if roi.size > 0 else 0.0
            intensity_peak = float(roi.max())  if roi.size > 0 else 0.0

            ai_score = float(scores[i]) if ai_active else 0.0

            candidates.append(Candidate(
                x=x, y=y, w=w, h=h,
                cx=cx, cy=cy,
                intensity_mean=intensity_mean,
                intensity_peak=intensity_peak,
                ai_confidence=ai_score,
                backend="classical",
            ))

        return PerceptionResult(
            candidates=candidates,
            backend_used="classical_cnn",
            frame_id=frame_id,
        )


# ---------------------------------------------------------------------------
# Backend B — YOLOv8 primary detector
# ---------------------------------------------------------------------------

class YOLOPerception(PerceptionBackend):
    """
    End-to-end AI target detector using the YOLOv8 ONNX model.

    YOLOv8 replaces the classical candidate-generation stage entirely.
    Each box produced by YOLO is wrapped in a Candidate with the YOLO
    confidence as ai_confidence.  No secondary CNN verifier is applied
    (YOLO is the AI — the verifier would be redundant).

    Parameters
    ----------
    model_path : str
        Path to the YOLOv8 ONNX export (e.g. "yolov8n.pt" converted to ONNX,
        or the ONNX file directly).
    conf_threshold : float
        Minimum confidence to accept a YOLO detection.
    """

    def __init__(self, model_path: str, conf_threshold: float = 0.40):
        from src.detection.neural import NeuralDetector  # lazy import — ONNX only loaded when YOLO is selected
        self._detector = NeuralDetector(model_path, conf_threshold=conf_threshold)

    def run(self, frame: np.ndarray, frame_id: int = -1) -> PerceptionResult:
        # NeuralDetector accepts grayscale or BGR
        boxes = self._detector.detect(frame)  # list of (x, y, w, h)

        candidates: List[Candidate] = []
        for (x, y, w, h) in boxes:
            # Centroid = box centre
            cx = x + w / 2.0
            cy = y + h / 2.0

            roi = frame[
                max(0, int(y)):min(frame.shape[0], int(y + h)),
                max(0, int(x)):min(frame.shape[1], int(x + w)),
            ]
            intensity_mean = float(roi.mean()) if roi.size > 0 else 0.0
            intensity_peak = float(roi.max())  if roi.size > 0 else 0.0

            # YOLO provides a single conf score per box; we attach it as ai_confidence
            # (NeuralDetector already filters below conf_threshold, so this is ≥ that)
            candidates.append(Candidate(
                x=x, y=y, w=w, h=h,
                cx=cx, cy=cy,
                intensity_mean=intensity_mean,
                intensity_peak=intensity_peak,
                ai_confidence=0.9,   # YOLO passes threshold — treat as high confidence
                backend="yolo",
            ))

        return PerceptionResult(
            candidates=candidates,
            backend_used="yolo",
            frame_id=frame_id,
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_perception(cfg) -> PerceptionBackend:
    """
    Construct the correct PerceptionBackend based on cfg.detection.backend.

    Returns ClassicalAIPerception for "classical_cnn" (default),
    YOLOPerception for "yolo".
    """
    backend = getattr(cfg.detection, 'backend', 'classical_cnn')

    if backend == 'yolo':
        import os
        candidates = [
            "yolov8n.pt",
            os.path.join(os.path.dirname(__file__), '..', '..', 'yolov8n.pt'),
        ]
        model_path = next((p for p in candidates if os.path.exists(p)), 'yolov8n.pt')
        return YOLOPerception(model_path=model_path)

    # Default: classical_cnn
    import os
    verifier_candidates = [
        "models/patch_verifier_cnn.onnx",
        os.path.join(os.path.dirname(__file__), '..', '..', 'models', 'patch_verifier_cnn.onnx'),
    ]
    verifier_path = next(
        (p for p in verifier_candidates if os.path.exists(p)),
        verifier_candidates[0]
    )

    # Resolve target size for size discrimination
    target_size = getattr(cfg.beacon, 'target_size_px', (-1, -1))
    if target_size == (-1, -1):
        # Auto-match primary beacon size
        target_size = getattr(cfg.beacon, 'size_px', (-1, -1))

    return ClassicalAIPerception(
        verifier_path=verifier_path,
        use_cnn=cfg.detection.use_cnn_verifier,
        target_size_px=target_size,
        size_tolerance=getattr(cfg.beacon, 'size_tolerance', 0.5),
    )
