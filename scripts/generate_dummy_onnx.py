import torch
import torch.nn as nn

class DummyDetector(nn.Module):
    def __init__(self):
        super().__init__()
        # A simple linear layer just so the model has some weights
        self.fc = nn.Linear(256 * 256, 1)

    def forward(self, x):
        # x is [batch, 1, 256, 256]
        batch_size = x.shape[0]
        
        # We always output one dummy bounding box with low confidence
        # Shape: [batch, num_boxes, 5] (x, y, w, h, conf)
        # We'll just hardcode a box at the center
        out = torch.zeros((batch_size, 1, 5), dtype=torch.float32)
        out[:, 0, 0] = 128.0 # x center
        out[:, 0, 1] = 128.0 # y center
        out[:, 0, 2] = 20.0  # w
        out[:, 0, 3] = 20.0  # h
        out[:, 0, 4] = 0.99  # high confidence so it always detects
        
        # Use the linear layer so it's a valid graph with parameters
        dummy_val = self.fc(x.view(batch_size, -1))
        out[:, 0, 0] += dummy_val[:, 0] * 0.0 # multiply by 0 to keep it constant
        
        return out

if __name__ == "__main__":
    import os
    os.makedirs("models", exist_ok=True)
    
    model = DummyDetector()
    model.eval()
    
    dummy_input = torch.randn(1, 1, 256, 256)
    
    torch.onnx.export(
        model, 
        dummy_input, 
        "models/dummy_detector.onnx", 
        export_params=True,
        opset_version=11,
        do_constant_folding=True,
        input_names=['input'],
        output_names=['output'],
        dynamic_axes={'input': {0: 'batch_size'}, 'output': {0: 'batch_size'}}
    )
    print("Exported models/dummy_detector.onnx")
