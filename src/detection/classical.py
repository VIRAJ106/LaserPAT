import cv2
import numpy as np
from typing import Tuple, List, Optional


def extract_candidates(image: np.ndarray, threshold: int = 80,
                       min_area: int = 3, max_area: int = 2000
                       ) -> List[Tuple[float, float, float, float]]:
    """
    Classical detection pipeline:
    1. Median Blur (crush salt & pepper noise)
    2. Threshold
    3. Connected Components
    Returns a list of candidate bounding boxes: (x, y, w, h).
    """
    # 1. Denoise
    # 3x3 median filter is very effective against salt & pepper
    denoised = cv2.medianBlur(image, 3)
    
    # 2. Threshold
    _, thresh = cv2.threshold(denoised, threshold, 255, cv2.THRESH_BINARY)
    
    # 3. Connected Components
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(thresh, connectivity=8)
    
    candidates = []
    # label 0 is background
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if min_area <= area <= max_area:
            x = stats[i, cv2.CC_STAT_LEFT]
            y = stats[i, cv2.CC_STAT_TOP]
            w = stats[i, cv2.CC_STAT_WIDTH]
            h = stats[i, cv2.CC_STAT_HEIGHT]
            candidates.append((float(x), float(y), float(w), float(h)))
            
    return candidates


def size_discriminate(
    candidates: List[Tuple[float, float, float, float]],
    target_w: float,
    target_h: float,
    tolerance: float = 0.5,
) -> List[Tuple[float, float, float, float]]:
    """
    Filter candidates by bounding-box size match.

    This is the multi-beacon discriminator: when multiple light sources are
    visible in the FOV (e.g. 3 beacons of different sizes), only the blob
    whose width and height both fall within ``tolerance`` of the user-specified
    target size is kept.

    Parameters
    ----------
    candidates : list of (x, y, w, h) from extract_candidates()
    target_w   : expected bounding-box width  of the target (px)
    target_h   : expected bounding-box height of the target (px)
    tolerance  : fractional half-width of the acceptance band.
                 0.5 → accept blobs within [target*0.5, target*1.5].
                 Larger values are more permissive (useful under heavy noise).

    Returns
    -------
    Filtered sub-list of candidates whose bounding box matches target size.
    If no candidates survive, returns the original list unchanged so the
    tracker can still attempt to lock (graceful fallback).
    """
    if target_w <= 0 or target_h <= 0:
        # Size discrimination disabled — pass all candidates through
        return candidates

    lo_w = target_w * (1.0 - tolerance)
    hi_w = target_w * (1.0 + tolerance)
    lo_h = target_h * (1.0 - tolerance)
    hi_h = target_h * (1.0 + tolerance)

    matched = [
        c for c in candidates
        if lo_w <= c[2] <= hi_w and lo_h <= c[3] <= hi_h
    ]

    # Do not gracefully fallback to noise if nothing matches.
    # If it doesn't match the size, it's not the target.
    return matched


def calculate_centroid(image: np.ndarray, bbox: Tuple[float, float, float, float]) -> Tuple[float, float]:
    """
    Calculates sub-pixel centroid using intensity weighting within the bounding box.
    """
    x, y, w, h = [int(v) for v in bbox]
    
    # Extract ROI
    roi = image[y:y+h, x:x+w].astype(np.float32)
    
    # Intensity weighted moments
    total_intensity = np.sum(roi)
    if total_intensity == 0:
        return (x + w/2.0, y + h/2.0)
        
    Y, X = np.indices(roi.shape)
    cx = np.sum(X * roi) / total_intensity
    cy = np.sum(Y * roi) / total_intensity
    
    return (x + cx, y + cy)
