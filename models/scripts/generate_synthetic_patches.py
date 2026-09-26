import os
import sys
import numpy as np
import cv2
import argparse

# Ensure we can import from src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.disturbances.noise import apply_sensor_noise

def create_synthetic_dataset(out_dir: str, num_samples: int = 10000, patch_size: int = 32):
    os.makedirs(out_dir, exist_ok=True)
    
    images = []
    labels = []
    
    for i in range(num_samples):
        # 0 = noise/speckle, 1 = beacon
        label = 1 if i < num_samples // 2 else 0
        
        # Base image (black background, possibly some ambient glow)
        patch = np.zeros((patch_size, patch_size), dtype=np.uint16)
        
        if label == 1:
            # Draw a beacon (2D Gaussian)
            # Simulate centroiding jitter (-4 to +4 pixels from center)
            cx = patch_size / 2 + np.random.uniform(-4, 4)
            cy = patch_size / 2 + np.random.uniform(-4, 4)
            
            # Simulate different distances (size variations)
            w = np.random.uniform(4, 12)
            h = np.random.uniform(4, 12)
            sigma_x = w / 4.0
            sigma_y = h / 4.0
            
            # Intensity varies based on simulated attenuation
            intensity = np.random.uniform(100, 255)
            
            Y, X = np.ogrid[0:patch_size, 0:patch_size]
            dist = ((X - cx)**2) / (2 * sigma_x**2) + ((Y - cy)**2) / (2 * sigma_y**2)
            gaussian = np.exp(-dist) * intensity
            patch = (patch + gaussian).astype(np.uint16)
            
        else:
            # Maybe add some structured noise or fake speckles that classical detector might pick up
            if np.random.rand() > 0.5:
                # Add a fake speckle (sharp, small)
                cx = np.random.uniform(4, patch_size-4)
                cy = np.random.uniform(4, patch_size-4)
                w = np.random.uniform(1, 3)
                sigma = w / 4.0
                intensity = np.random.uniform(50, 150)
                Y, X = np.ogrid[0:patch_size, 0:patch_size]
                dist = ((X - cx)**2 + (Y - cy)**2) / (2 * sigma**2)
                gaussian = np.exp(-dist) * intensity
                patch = (patch + gaussian).astype(np.uint16)
                
        # Clip to 255
        patch_u8 = np.clip(patch, 0, 255).astype(np.uint8)
        
        # Apply environmental noise
        gaussian_sigma = np.random.uniform(0, 30)
        poisson = np.random.choice([True, False])
        sp_percent = np.random.uniform(0, 2)
        
        noisy_patch = apply_sensor_noise(patch_u8, gaussian_sigma, poisson, sp_percent)
        
        images.append(noisy_patch)
        labels.append(label)
        
        if (i+1) % 1000 == 0:
            print(f"Generated {i+1}/{num_samples} patches")
            
    images = np.array(images, dtype=np.uint8)
    labels = np.array(labels, dtype=np.uint8)
    
    # Shuffle
    idx = np.random.permutation(num_samples)
    images = images[idx]
    labels = labels[idx]
    
    out_file = os.path.join(out_dir, "synthetic_dataset.npz")
    np.savez_compressed(out_file, images=images, labels=labels)
    print(f"Saved dataset to {out_file} with shape {images.shape}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=str, default="models/dataset")
    parser.add_argument("--samples", type=int, default=10000)
    args = parser.parse_args()
    
    print("Generating synthetic patches...")
    create_synthetic_dataset(args.out, args.samples)
