"""Run plate detection on a folder of images from the command line.

    python -m src.detect                 # uses test_images/
    python -m src.detect path/to/images  # or a folder / single file
"""

import argparse
import logging
from pathlib import Path

import cv2

from .config import ROOT, setup_logging
from .pipeline import PlatePipeline

log = logging.getLogger("detect")

IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def image_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    return sorted(p for p in target.iterdir() if p.suffix.lower() in IMAGE_TYPES)


def main():
    parser = argparse.ArgumentParser(description="Detect number plates in images")
    parser.add_argument("target", nargs="?", default=str(ROOT / "test_images"))
    parser.add_argument("-v", "--verbose", action="store_true", help="show every OCR read")
    args = parser.parse_args()

    setup_logging("DEBUG" if args.verbose else None)

    target = Path(args.target)
    if not target.exists():
        parser.error(f"{target} does not exist")

    pipeline = PlatePipeline().load()

    for path in image_files(target):
        img = cv2.imread(str(path))
        if img is None:
            log.error("Could not read %s", path.name)
            continue

        plates = pipeline.detect(img)
        if not plates:
            log.info("%s: no plate found", path.name)
        for p in plates:
            status = "needs review" if p.needs_review else f"valid {p.format}"
            log.info("%s: %s (%s, det %.2f, ocr %.2f)", path.name, p.text or "<unreadable>",
                     status, p.det_conf, p.ocr_conf)


if __name__ == "__main__":
    main()
