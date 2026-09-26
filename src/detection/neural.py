"""
neural.py — AI-based primary target detector using YOLOv8 ONNX.

Architecture:
  Primary path  : YOLOv8n (ONNX) — end-to-end AI object detection
  Fallback path : OpenCV classical CV + CNN patch verifier (if YOLO absent/fails)

YOLOv8 ONNX output format:
  shape [1, 5, 8400]  (transposed compared to older YOLO)
  Row layout: [x_center, y_center, width, height, conf]
  Already normalised to input size (640×640).
"""
import onnxruntime as ort
import numpy as np
import cv2
from typing import Tuple, List


class NeuralDetector:
    """
    Primary AI target detector backed by a YOLOv8 ONNX export.

    Input  : single-channel (grayscale) or 3-channel BGR uint8 image
    Output : list of (x, y, w, h) bounding boxes in *pixel* coordinates,
             relative to the input image's original size.
    """

    # YOLOv8n default input size
    YOLO_INPUT_SIZE = 640

    def __init__(self, model_path: str, conf_threshold: float = 0.40):
        self.model_path = model_path
        self.conf_threshold = conf_threshold

        sess_opts = ort.SessionOptions()
        sess_opts.intra_op_num_threads = 2          # Keep CPU usage reasonable
        sess_opts.graph_optimization_level = (
            ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        )
        self.session = ort.InferenceSession(
            self.model_path,
            sess_options=sess_opts,
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )

        self.input_name = self.session.get_inputs()[0].name
        inp_shape = self.session.get_inputs()[0].shape
        # Resolve dynamic dims  [batch, C, H, W]
        self.input_h = inp_shape[2] if isinstance(inp_shape[2], int) else self.YOLO_INPUT_SIZE
        self.input_w = inp_shape[3] if isinstance(inp_shape[3], int) else self.YOLO_INPUT_SIZE

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #
    def detect(self, image: np.ndarray) -> List[Tuple[float, float, float, float]]:
        """
        Run YOLOv8 inference.

        Args:
            image: Grayscale (H×W) or BGR (H×W×3) uint8 frame.

        Returns:
            List of (x, y, w, h) top-left + size bounding boxes in original
            pixel coordinates, one per detected beacon candidate.
        """
        orig_h, orig_w = image.shape[:2]

        # ── Pre-processing ────────────────────────────────────────────────
        # YOLOv8 expects RGB 3-channel input
        if image.ndim == 2:
            rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
        elif image.shape[2] == 4:
            rgb = cv2.cvtColor(image, cv2.COLOR_BGRA2RGB)
        else:
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        # Letterbox resize to keep aspect ratio (avoids distortion)
        img_resized, (pad_x, pad_y), scale = self._letterbox(
            rgb, (self.input_h, self.input_w)
        )

        # NCHW float32 normalised [0, 1]
        tensor = img_resized.astype(np.float32) / 255.0
        tensor = np.transpose(tensor, (2, 0, 1))   # HWC → CHW
        tensor = np.expand_dims(tensor, axis=0)    # CHW → NCHW

        # ── Inference ─────────────────────────────────────────────────────
        raw = self.session.run(None, {self.input_name: tensor})[0]

        # ── Post-processing ────────────────────────────────────────────────
        # YOLOv8 output: [1, 4+num_classes, 8400]  (transposed anchors)
        # We transpose to [8400, 4+num_classes] for easier iteration
        preds = raw[0]                    # [5, 8400]  (for single-class model)
        preds = preds.T                   # [8400, 5]

        candidates: List[Tuple[float, float, float, float]] = []
        for pred in preds:
            # For single-class beacon model: layout is [xc, yc, w, h, conf]
            # For multi-class COCO model   : conf = max(class_scores) after idx 4
            if len(pred) == 5:
                conf = float(pred[4])
            else:
                conf = float(pred[4:].max())

            if conf < self.conf_threshold:
                continue

            xc, yc, bw, bh = pred[:4]

            # Un-letterbox: remove padding, un-scale back to original coords
            xc = (xc - pad_x) / scale
            yc = (yc - pad_y) / scale
            bw = bw / scale
            bh = bh / scale

            # Clamp to original image bounds
            x = max(0.0, float(xc - bw / 2.0))
            y = max(0.0, float(yc - bh / 2.0))
            w = min(float(bw), float(orig_w - x))
            h = min(float(bh), float(orig_h - y))

            candidates.append((x, y, w, h))

        return candidates

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _letterbox(
        img: np.ndarray,
        target_shape: Tuple[int, int],
        color: Tuple[int, int, int] = (114, 114, 114),
    ) -> Tuple[np.ndarray, Tuple[float, float], float]:
        """
        Resize *img* to *target_shape* with letterboxing.

        Returns:
            (padded_image, (pad_x, pad_y), scale)
              pad_x / pad_y are the pixel offsets added on each side,
              scale is the uniform scaling factor applied.
        """
        th, tw = target_shape
        ih, iw = img.shape[:2]
        scale = min(tw / iw, th / ih)

        new_w = int(round(iw * scale))
        new_h = int(round(ih * scale))
        resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        pad_x = (tw - new_w) / 2.0
        pad_y = (th - new_h) / 2.0
        top, bottom = int(round(pad_y - 0.1)), int(round(pad_y + 0.1))
        left, right = int(round(pad_x - 0.1)), int(round(pad_x + 0.1))

        padded = cv2.copyMakeBorder(
            resized, top, bottom, left, right,
            cv2.BORDER_CONSTANT, value=color,
        )
        return padded, (pad_x, pad_y), scale
