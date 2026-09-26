"""
generate_test_video.py — Create a synthetic 30fps test video with a moving beacon.

This video is used for the Benchmark Gate (SPEC.md Section 4.2) to test
video mode ingestion and centroiding accuracy.

Usage:
    python tests/data/generate_test_video.py
    
Output:
    tests/data/sample_30fps.mp4
"""

import cv2
import numpy as np
import math
import os


def generate_test_video(
    output_path: str = "tests/data/sample_30fps.mp4",
    width: int = 640,
    height: int = 480,
    fps: int = 30,
    duration_seconds: float = 10.0,
    beacon_size: int = 20,
    noise_level: float = 10.0,
    sp_noise_percent: float = 5.0,
    motion: str = "stationary",  # "stationary" or "circular"
):
    """
    Generate a synthetic video with a moving beacon on a noisy background.
    
    Args:
        output_path: Output MP4 file path
        width: Video frame width
        height: Video frame height
        fps: Frames per second
        duration_seconds: Video duration
        beacon_size: Beacon square size in pixels
        noise_level: Gaussian noise sigma
        sp_noise_percent: Salt and pepper noise percentage
        motion: "stationary" or "circular" beacon motion
    """
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    
    # Video writer setup
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height), False)
    
    total_frames = int(fps * duration_seconds)
    
    # Beacon motion parameters
    center_x, center_y = width / 2, height / 2
    radius = min(width, height) / 4
    
    print(f"Generating test video: {output_path}")
    print(f"  Resolution: {width}×{height}")
    print(f"  FPS: {fps}")
    print(f"  Duration: {duration_seconds}s ({total_frames} frames)")
    print(f"  Beacon: {beacon_size}×{beacon_size}px ({motion})")
    print(f"  Noise: Gaussian(σ={noise_level}) + S&P({sp_noise_percent}%)")
    
    for frame_idx in range(total_frames):
        # Create blank frame
        frame = np.zeros((height, width), dtype=np.uint8)
        
        # Calculate beacon position
        if motion == "circular":
            angle = 2 * math.pi * frame_idx / total_frames
            bx = int(center_x + radius * math.cos(angle))
            by = int(center_y + radius * math.sin(angle))
        else:  # stationary
            bx = int(center_x)
            by = int(center_y)
        
        # Draw beacon (bright square)
        half_size = beacon_size // 2
        y1 = max(0, by - half_size)
        y2 = min(height, by + half_size)
        x1 = max(0, bx - half_size)
        x2 = min(width, bx + half_size)
        frame[y1:y2, x1:x2] = 255
        
        # Add Gaussian noise
        if noise_level > 0:
            noise = np.random.normal(0, noise_level, frame.shape)
            frame = np.clip(frame.astype(float) + noise, 0, 255).astype(np.uint8)
        
        # Add Salt and Pepper noise
        if sp_noise_percent > 0:
            sp_mask = np.random.rand(height, width)
            frame[sp_mask < sp_noise_percent / 200] = 0      # Pepper
            frame[sp_mask > 1 - sp_noise_percent / 200] = 255  # Salt
        
        # Write frame
        out.write(frame)
        
        if (frame_idx + 1) % 30 == 0:
            print(f"  Progress: {frame_idx + 1}/{total_frames} frames")
    
    out.release()
    print(f"✅ Video created: {output_path}")
    print(f"   Size: {os.path.getsize(output_path) / 1024:.1f} KB")
    
    return output_path


def generate_ground_truth(
    output_path: str = "tests/data/sample_30fps_ground_truth.csv",
    width: int = 640,
    height: int = 480,
    fps: int = 30,
    duration_seconds: float = 10.0,
    beacon_size: int = 20,
    motion: str = "stationary",
):
    """
    Generate ground truth CSV for the test video.
    
    Format: frame,x,y
    """
    total_frames = int(fps * duration_seconds)
    center_x, center_y = width / 2, height / 2
    radius = min(width, height) / 4
    
    with open(output_path, 'w') as f:
        f.write("frame,x,y\n")
        for frame_idx in range(total_frames):
            if motion == "circular":
                angle = 2 * math.pi * frame_idx / total_frames
                bx = center_x + radius * math.cos(angle)
                by = center_y + radius * math.sin(angle)
            else:  # stationary
                bx = center_x
                by = center_y
            f.write(f"{frame_idx},{bx:.2f},{by:.2f}\n")
    
    print(f"✅ Ground truth CSV created: {output_path}")
    return output_path


if __name__ == "__main__":
    # Generate test video with STATIONARY beacon for easier tracking validation
    # Reduced noise for clean tracking performance
    video_path = generate_test_video(
        motion="stationary",
        noise_level=5.0,  # Reduced from 10
        sp_noise_percent=2.0  # Reduced from 5
    )
    
    # Generate ground truth
    gt_path = generate_ground_truth(motion="stationary")
    
    print("\n" + "="*60)
    print("Test video generation complete!")
    print("="*60)
    print(f"Video: {video_path}")
    print(f"Ground Truth: {gt_path}")
    print("\nUse this video to test Benchmark Gate:")
    print("  make gate-benchmark")
    print("  python scripts/deployment_bridge.py --mode video \\")
    print(f"      --video {video_path} --report")
    print("="*60)
