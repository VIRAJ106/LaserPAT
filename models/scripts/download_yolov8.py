"""
download_yolov8.py — One-time script to export YOLOv8n to ONNX.

Run once:
    python models/scripts/download_yolov8.py

This downloads the pretrained YOLOv8n weights from Ultralytics (~6 MB)
and exports them as a single-file ONNX model to models/yolov8n.onnx.

For production: replace with a model fine-tuned on beacon/laser-spot data.
"""
import os
import sys

def main():
    try:
        from ultralytics import YOLO
    except ImportError:
        print("ultralytics not installed. Run: pip install ultralytics")
        sys.exit(1)

    output_path = os.path.join(
        os.path.dirname(__file__), "..", "yolov8n.onnx"
    )
    output_path = os.path.normpath(output_path)

    if os.path.exists(output_path):
        print(f"[OK] YOLOv8n ONNX already exists at {output_path}")
        return

    print("[INFO] Downloading YOLOv8n weights and exporting to ONNX...")
    model = YOLO("yolov8n.pt")   # downloads ~6 MB on first run
    model.export(format="onnx", imgsz=640, simplify=True, opset=17)

    # Ultralytics saves to <cwd>/yolov8n.onnx by default — move it
    default_out = "yolov8n.onnx"
    if os.path.exists(default_out) and not os.path.exists(output_path):
        import shutil
        shutil.move(default_out, output_path)

    if os.path.exists(output_path):
        print(f"[OK] Saved: {output_path}")
    else:
        print(f"[WARN] Could not move file, check {default_out}")


if __name__ == "__main__":
    main()
