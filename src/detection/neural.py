import onnxruntime as ort
import numpy as np
import cv2
from typing import Tuple, List

class NeuralDetector:
    """
    ONNX-based Neural Network Detector.
    Expects a YOLO-like output or a simple bounding box regression model.
    """
    def __init__(self, model_path: str, conf_threshold: float = 0.5):
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        # Start session
        self.session = ort.InferenceSession(self.model_path)
        self.input_name = self.session.get_inputs()[0].name
        
        # Get expected input shape
        input_shape = self.session.get_inputs()[0].shape
        # typical format: [batch, channels, height, width]
        self.input_h = input_shape[2] if isinstance(input_shape[2], int) else 256
        self.input_w = input_shape[3] if isinstance(input_shape[3], int) else 256
        
    def detect(self, image: np.ndarray) -> List[Tuple[float, float, float, float]]:
        """
        Runs the ONNX model and returns a list of bounding boxes (x, y, w, h).
        """
        # Preprocess
        original_h, original_w = image.shape
        resized = cv2.resize(image, (self.input_w, self.input_h))
        
        # Convert to NCHW float32
        tensor = resized.astype(np.float32) / 255.0
        tensor = np.expand_dims(tensor, axis=0) # Add channel dim
        tensor = np.expand_dims(tensor, axis=0) # Add batch dim
        
        # Run inference
        outputs = self.session.run(None, {self.input_name: tensor})
        
        # Assuming output is shape [1, num_boxes, 5] -> [x_center, y_center, w, h, conf]
        # Needs mapping to original resolution
        preds = outputs[0][0] # shape [num_boxes, 5]
        
        candidates = []
        for pred in preds:
            conf = pred[4]
            if conf >= self.conf_threshold:
                # Map back to original image scale
                x_c = pred[0] * (original_w / self.input_w)
                y_c = pred[1] * (original_h / self.input_h)
                w = pred[2] * (original_w / self.input_w)
                h = pred[3] * (original_h / self.input_h)
                
                # Convert center to top-left
                x = x_c - w/2.0
                y = y_c - h/2.0
                
                candidates.append((float(x), float(y), float(w), float(h)))
                
        return candidates
