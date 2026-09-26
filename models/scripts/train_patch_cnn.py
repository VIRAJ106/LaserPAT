import os
import argparse
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import TensorDataset, DataLoader

class TinyPatchCNN(nn.Module):
    """
    A lightweight 3-layer CNN designed to quickly verify if a 32x32 patch 
    contains a beacon (1) or noise (0).
    """
    def __init__(self):
        super(TinyPatchCNN, self).__init__()
        
        # Input is 1x32x32
        self.conv1 = nn.Conv2d(1, 8, kernel_size=3, padding=1)
        self.relu1 = nn.ReLU()
        self.pool1 = nn.MaxPool2d(2) # 8x16x16
        
        self.conv2 = nn.Conv2d(8, 16, kernel_size=3, padding=1)
        self.relu2 = nn.ReLU()
        self.pool2 = nn.MaxPool2d(2) # 16x8x8
        
        self.conv3 = nn.Conv2d(16, 16, kernel_size=3, padding=1)
        self.relu3 = nn.ReLU()
        self.pool3 = nn.MaxPool2d(2) # 16x4x4
        
        self.flatten = nn.Flatten()
        self.fc1 = nn.Linear(16 * 4 * 4, 32)
        self.relu4 = nn.ReLU()
        self.fc2 = nn.Linear(32, 1) # Output raw logit (will use BCEWithLogitsLoss)

    def forward(self, x):
        x = self.pool1(self.relu1(self.conv1(x)))
        x = self.pool2(self.relu2(self.conv2(x)))
        x = self.pool3(self.relu3(self.conv3(x)))
        x = self.flatten(x)
        x = self.relu4(self.fc1(x))
        x = self.fc2(x)
        return x

def train_model(dataset_path: str, out_onnx: str, epochs: int = 5, batch_size: int = 64):
    print(f"Loading dataset from {dataset_path}...")
    data = np.load(dataset_path)
    images = data['images']
    labels = data['labels']
    
    # Normalize images from 0-255 uint8 to 0-1 float32
    images = images.astype(np.float32) / 255.0
    # Add channel dimension: (N, 1, 32, 32)
    images = np.expand_dims(images, axis=1)
    
    labels = labels.astype(np.float32).reshape(-1, 1)
    
    # Split into train/val (80/20)
    split_idx = int(0.8 * len(images))
    x_train, y_train = images[:split_idx], labels[:split_idx]
    x_val, y_val = images[split_idx:], labels[split_idx:]
    
    print(f"Train size: {len(x_train)}, Val size: {len(x_val)}")
    
    train_dataset = TensorDataset(torch.tensor(x_train), torch.tensor(y_train))
    val_dataset = TensorDataset(torch.tensor(x_val), torch.tensor(y_val))
    
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
    
    model = TinyPatchCNN()
    criterion = nn.BCEWithLogitsLoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    
    print("Starting training...")
    for epoch in range(epochs):
        model.train()
        train_loss = 0.0
        for batch_x, batch_y in train_loader:
            optimizer.zero_grad()
            outputs = model(batch_x)
            loss = criterion(outputs, batch_y)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * batch_x.size(0)
            
        train_loss /= len(train_loader.dataset)
        
        # Validation
        model.eval()
        val_loss = 0.0
        correct = 0
        total = 0
        with torch.no_grad():
            for batch_x, batch_y in val_loader:
                outputs = model(batch_x)
                loss = criterion(outputs, batch_y)
                val_loss += loss.item() * batch_x.size(0)
                
                predicted = (torch.sigmoid(outputs) > 0.5).float()
                total += batch_y.size(0)
                correct += (predicted == batch_y).sum().item()
                
        val_loss /= len(val_loader.dataset)
        accuracy = 100 * correct / total
        
        print(f"Epoch {epoch+1}/{epochs} | Train Loss: {train_loss:.4f} | Val Loss: {val_loss:.4f} | Val Acc: {accuracy:.2f}%")
        
    # Export to ONNX
    print(f"Exporting model to {out_onnx}...")
    model.eval()
    dummy_input = torch.randn(1, 1, 32, 32, dtype=torch.float32)
    os.makedirs(os.path.dirname(out_onnx), exist_ok=True)
    
    torch.onnx.export(
        model, 
        dummy_input, 
        out_onnx, 
        export_params=True,
        opset_version=11,
        do_constant_folding=True,
        input_names=['input'],
        output_names=['output'],
        dynamic_axes={'input': {0: 'batch_size'}, 'output': {0: 'batch_size'}}
    )
    print("Done!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=str, default="models/dataset/synthetic_dataset.npz")
    parser.add_argument("--out", type=str, default="models/patch_verifier_cnn.onnx")
    parser.add_argument("--epochs", type=int, default=5)
    args = parser.parse_args()
    
    train_model(args.dataset, args.out, args.epochs)
