import os
import onnxruntime as ort
import numpy as np
import cv2
from typing import List

def sigmoid(x):
    return 1 / (1 + np.exp(-x))

class AIVerifier:
    """
    Patch-based CNN Verifier for candidate centroid verification.
    Takes 32x32 image patches around candidates and returns confidence scores.

    If the ONNX model file is not found, the verifier degrades gracefully to
    classical-only mode (returns 0.0 for all candidates) rather than crashing.
    Run `make train` to regenerate the model if it is missing.
    """
    def __init__(self, model_path: str, patch_size: int = 32):
        self.model_path = model_path
        self.patch_size = patch_size
        self._available = False

        if os.path.exists(model_path):
            self.session = ort.InferenceSession(self.model_path)
            self.input_name = self.session.get_inputs()[0].name
            self._available = True
        else:
            print(f"[AIVerifier] WARNING: model not found at '{model_path}'. "
                  "CNN verification disabled \u2014 run `make train` to generate it. "
                  "Falling back to classical-only detection (score=0.0).")

    def verify_patches(self, patches: List[np.ndarray]) -> List[float]:
        """
        Runs the tiny CNN on a batch of patches.
        Returns a list of confidence scores [0.0, 1.0].
        Returns all-zeros if model is unavailable.
        """
        if not self._available or not patches:
            return [0.0] * len(patches)

        # Ensure correct shape and type
        batch = []
        for p in patches:
            if p.shape != (self.patch_size, self.patch_size):
                p = cv2.resize(p, (self.patch_size, self.patch_size))
            batch.append(p)

        batch_array = np.array(batch, dtype=np.float32) / 255.0

        # Add channel dimension -> (N, 1, 32, 32)
        batch_array = np.expand_dims(batch_array, axis=1)

        # Run inference
        outputs = self.session.run(None, {self.input_name: batch_array})

        # outputs[0] is shape (N, 1) -> raw logits
        logits = outputs[0].flatten()

        # Convert to probabilities
        probs = sigmoid(logits)

        return probs.tolist()

    def extract_and_verify(self, full_image: np.ndarray, centroids: List[tuple]) -> List[float]:
        """
        Helper method to extract patches around (x, y) centroids and verify them.
        """
        h, w = full_image.shape
        half_p = self.patch_size // 2
        
        patches = []
        for (cx, cy) in centroids:
            # integer coordinates
            ix, iy = int(round(cx)), int(round(cy))
            
            # calculate boundaries
            x1, x2 = ix - half_p, ix + half_p
            y1, y2 = iy - half_p, iy + half_p
            
            # handle edge cases by padding if necessary
            if x1 < 0 or y1 < 0 or x2 > w or y2 > h:
                # simpler to pad the whole image first, but let's just pad this patch
                patch = np.zeros((self.patch_size, self.patch_size), dtype=full_image.dtype)
                
                # Image slice coords
                img_x1, img_x2 = max(0, x1), min(w, x2)
                img_y1, img_y2 = max(0, y1), min(h, y2)
                
                # Patch slice coords
                p_x1 = max(0, -x1)
                p_y1 = max(0, -y1)
                p_x2 = p_x1 + (img_x2 - img_x1)
                p_y2 = p_y1 + (img_y2 - img_y1)
                
                patch[p_y1:p_y2, p_x1:p_x2] = full_image[img_y1:img_y2, img_x1:img_x2]
            else:
                patch = full_image[y1:y2, x1:x2]
                
            patches.append(patch)
            
        return self.verify_patches(patches)
