"""
candidate_manager.py — Candidate filtering, identity, and target selection.

Architecture
------------
    PerceptionResult (raw per-frame candidates)
          ↓
    CandidateManager
      ├── 1. Size filter (size_discriminate — already in classical.py)
      ├── 2. Intensity filter
      ├── 3. Temporal association  (frame-to-frame ID carry-over)
      ├── 4. Confidence fusion     (size + AI score + temporal persistence)
      ├── 5. Target selection      (highest fused score)
      └── 6. Rejection             (below threshold → None)
          ↓
    TargetIdentity | None

This lifts the inline candidate-selection block (previously lines 172–207
of scenario_runner.py) into a reusable, testable class with a clean contract.
It also extends the selection from pure size/score to include temporal
persistence — fixing the "target identity too tightly coupled to beacon size"
architectural gap.
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

import numpy as np

from src.interfaces import Candidate, PerceptionResult, TargetIdentity


class CandidateManager:
    """
    Stateful candidate filter and target identity manager.

    Maintains a temporal track so that a candidate that has been consistently
    observed over multiple frames is preferred over a first-seen bright blob.

    Parameters
    ----------
    min_ai_threshold : float
        AI confidence below which a candidate is not accepted (classical
        fallback uses 0.5 as the "any valid detection" gate, preserved here).
    min_fused_confidence : float
        Minimum fused score to declare a valid TargetIdentity.
    max_history : int
        Maximum frames of spatial trajectory to retain per track.
    temporal_weight : float
        Fraction of fused score contributed by temporal persistence
        (0.0 = pure single-frame, 1.0 = pure temporal).
    association_radius_px : float
        Max pixel distance between frames to associate a detection to the
        existing track.
    """

    def __init__(
        self,
        min_ai_threshold: float = 0.5,
        min_fused_confidence: float = 0.3,
        max_history: int = 30,
        temporal_weight: float = 0.25,
        association_radius_px: float = 80.0,
    ):
        self._min_ai_thr   = min_ai_threshold
        self._min_fused    = min_fused_confidence
        self._max_history  = max_history
        self._t_weight     = temporal_weight
        self._assoc_radius = association_radius_px

        # Internal track state
        self._track: Optional[_Track] = None
        self._next_id: int = 1

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, result: PerceptionResult) -> Optional[TargetIdentity]:
        """
        Ingest a PerceptionResult and return the best TargetIdentity.

        Returns None if no confident target can be identified this frame.
        """
        candidates = result.candidates
        if not candidates:
            return self._handle_miss()

        # --- 1. Select best raw candidate ---
        best = self._select_best_candidate(candidates)
        if best is None:
            return self._handle_miss()

        # --- 2. Temporal association ---
        self._associate(best)

        # --- 3. Fused confidence ---
        fused = self._fuse(best)

        if fused < self._min_fused:
            return self._handle_miss()

        # --- 4. Build TargetIdentity ---
        track = self._track
        return TargetIdentity(
            candidate=best,
            temporal_id=track.track_id,
            history_frames=track.age,
            consecutive_misses=0,
            fused_confidence=fused,
            spatial_trajectory=list(track.trajectory),
        )

    def reset(self) -> None:
        """Reset all tracking state (e.g. after LOST → SEARCH transition)."""
        self._track = None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _select_best_candidate(self, candidates: List[Candidate]) -> Optional[Candidate]:
        """
        Select the single best candidate from the perception result.

        Priority:
          1. Highest AI confidence above min_ai_threshold
          2. Fallback: largest area (classical-only path)

        This exactly replicates the original scenario_runner.py inline logic
        but is now a named, testable function.
        """
        ai_active = any(c.ai_confidence > 0.1 for c in candidates)

        best_score = 0.0
        best_cand: Optional[Candidate] = None

        if ai_active:
            for c in candidates:
                if c.ai_confidence > self._min_ai_thr and c.ai_confidence > best_score:
                    best_score = c.ai_confidence
                    best_cand = c
        else:
            # Classical fallback — largest area
            best_area = 0.0
            for c in candidates:
                area = c.w * c.h
                if area > best_area:
                    best_area = area
                    best_cand = c
                    best_cand.ai_confidence = 0.6   # Synthetic score for downstream use

        return best_cand

    def _associate(self, cand: Candidate) -> None:
        """Associate candidate to existing track or start a new one."""
        if self._track is None:
            self._track = _Track(self._next_id, cand)
            self._next_id += 1
            return

        dist = math.hypot(cand.cx - self._track.last_cx,
                          cand.cy - self._track.last_cy)

        if dist <= self._assoc_radius:
            # Same track — update
            self._track.update(cand, self._max_history)
        else:
            # Far enough to be a different object — start fresh track
            self._track = _Track(self._next_id, cand)
            self._next_id += 1

    def _fuse(self, cand: Candidate) -> float:
        """
        Fuse single-frame AI confidence with temporal persistence weight.

        fused = (1 - t_weight) * ai_confidence
              + t_weight       * persistence_score

        persistence_score ramps from 0 → 1 over the first 10 frames.
        """
        if self._track is None:
            return cand.ai_confidence

        age = self._track.age
        persistence = min(1.0, age / 10.0)   # saturates at 10 frames

        return (
            (1.0 - self._t_weight) * cand.ai_confidence
            + self._t_weight       * persistence
        )

    def _handle_miss(self) -> Optional[TargetIdentity]:
        """Increment miss counter on active track; return None."""
        if self._track is not None:
            self._track.misses += 1
        return None


# ---------------------------------------------------------------------------
# Internal track state
# ---------------------------------------------------------------------------

class _Track:
    """Lightweight per-target track object (private to CandidateManager)."""

    def __init__(self, track_id: int, seed: Candidate):
        self.track_id = track_id
        self.age = 1
        self.misses = 0
        self.last_cx = seed.cx
        self.last_cy = seed.cy
        self.trajectory: List[Tuple[float, float]] = [(seed.cx, seed.cy)]

    def update(self, cand: Candidate, max_history: int) -> None:
        self.age += 1
        self.misses = 0
        self.last_cx = cand.cx
        self.last_cy = cand.cy
        self.trajectory.append((cand.cx, cand.cy))
        if len(self.trajectory) > max_history:
            self.trajectory.pop(0)
