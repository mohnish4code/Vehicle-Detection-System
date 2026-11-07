"""Train the plate detector.

Run from backend/:

    python -m scripts.train --data ../data/archive/dataset.yaml

The best weights end up in runs/detect/<name>/weights/best.pt. Copy that
file to models/best.pt to use it in the app.
"""

import argparse

from ultralytics import YOLO


def main():
    parser = argparse.ArgumentParser(description="Train the YOLOv8 number plate detector")
    parser.add_argument("--data", default="../data/archive/dataset.yaml", help="YOLO dataset yaml")
    parser.add_argument("--model", default="yolov8n.pt", help="starting weights")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    args = parser.parse_args()

    YOLO(args.model).train(data=args.data, epochs=args.epochs, imgsz=args.imgsz, batch=args.batch)


if __name__ == "__main__":
    main()
