"""Plate detection + OCR pipeline shared by the CLI and the web app."""

import logging
import time
from dataclasses import dataclass, field
from statistics import median

import cv2
import numpy as np

from .config import Settings, get_settings
from .plates import correct_plate, normalize

log = logging.getLogger(__name__)

PLATE_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


@dataclass
class OcrRead:
    text: str
    confidence: float
    valid: bool = False
    format: str | None = None
    raw: str = ""
    fixes: int = 0


@dataclass
class PlateResult:
    box: tuple[int, int, int, int]  # x1, y1, x2, y2 in image pixels
    det_conf: float
    text: str
    raw_text: str
    ocr_conf: float
    valid: bool  # text matches a plate format
    format: str | None
    needs_review: bool  # not valid, or valid but low confidence / heavily corrected
    crop: np.ndarray = field(repr=False)


def preprocess_variants(crop: np.ndarray, upscale: int = 2) -> list[np.ndarray]:
    """A few versions of the crop; different ones work better on different plates."""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    def big(img):
        return cv2.resize(img, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC)

    adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    _, blurred = cv2.threshold(cv2.GaussianBlur(gray, (5, 5), 0), 120, 255, cv2.THRESH_BINARY)

    return [big(gray), big(cv2.equalizeHist(gray)), big(adaptive), big(blurred)]


def group_rows(ocr_results, ignore_words=("IND",)) -> list[tuple[str, float]]:
    """Group EasyOCR boxes into text rows, top to bottom.

    ocr_results is EasyOCR's list of (bbox, text, prob). Returns one
    (text, confidence) per row, with boxes in a row read left to right.
    """
    ignore = {w.upper() for w in ignore_words}
    items = []
    for bbox, text, prob in ocr_results:
        text = normalize(text)
        if not text or text in ignore:
            continue
        ys = [p[1] for p in bbox]
        xs = [p[0] for p in bbox]
        items.append({
            "text": text,
            "prob": float(prob),
            "cy": (min(ys) + max(ys)) / 2,
            "h": max(ys) - min(ys),
            "x": min(xs),
        })

    if not items:
        return []

    # Boxes whose centres are within half a line height are on the same row
    tolerance = median(i["h"] for i in items) / 2
    rows: list[list[dict]] = []
    for item in sorted(items, key=lambda i: i["cy"]):
        if rows and abs(item["cy"] - rows[-1][-1]["cy"]) <= tolerance:
            rows[-1].append(item)
        else:
            rows.append([item])

    out = []
    for row in rows:
        row.sort(key=lambda i: i["x"])
        text = "".join(i["text"] for i in row)
        conf = sum(i["prob"] * len(i["text"]) for i in row) / len(text)
        out.append((text, conf))
    return out


def best_read(rows: list[tuple[str, float]]) -> OcrRead | None:
    """Pick the best plate text from the OCR rows of one image variant.

    Tries all rows joined (two row plates), then each run of consecutive
    rows, so stray text above or below the plate doesn't spoil the read.
    """
    if not rows:
        return None

    candidates = []
    for start in range(len(rows)):
        for end in range(start + 1, len(rows) + 1):
            chunk = rows[start:end]
            raw = "".join(t for t, _ in chunk)
            conf = sum(c * len(t) for t, c in chunk) / len(raw)
            match = correct_plate(raw)
            if match:
                candidates.append(OcrRead(match.text, conf, True, match.format, raw, match.fixes))
            else:
                candidates.append(OcrRead(raw, conf, False, None, raw))

    return max(candidates, key=read_rank)


def read_rank(read: OcrRead):
    # Valid plates first: longest, then fewest swaps, then most confident.
    # Invalid text is only a fallback, ranked the way the old code did (length * prob).
    if read.valid:
        return (1, len(read.text), -read.fixes, read.confidence)
    return (0, read.confidence * len(read.text), 0, read.confidence)


class PlatePipeline:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.model = None
        self.reader = None

    def load(self):
        """Load YOLO and EasyOCR. Slow, so do it once and reuse the pipeline."""
        from ultralytics import YOLO
        import easyocr

        weights = self.settings.path(self.settings.model.weights)
        if not weights.exists():
            raise FileNotFoundError(f"Model weights not found at {weights}")

        start = time.perf_counter()
        self.model = YOLO(str(weights))
        self.reader = easyocr.Reader(self.settings.ocr.languages, gpu=self.settings.ocr.gpu, verbose=False)
        log.info("Loaded model %s and OCR in %.1fs", weights.name, time.perf_counter() - start)
        return self

    @property
    def loaded(self) -> bool:
        return self.model is not None and self.reader is not None

    def read_text(self, crop: np.ndarray) -> OcrRead:
        ocr = self.settings.ocr
        reads = []
        for variant in preprocess_variants(crop, ocr.upscale):
            rows = group_rows(self.reader.readtext(variant, allowlist=PLATE_CHARS), ocr.ignore_words)
            read = best_read(rows)
            if read:
                log.debug("OCR variant read %r -> %r (conf %.2f)", read.raw, read.text, read.confidence)
                reads.append(read)

        if not reads:
            return OcrRead("", 0.0)
        return max(reads, key=read_rank)

    def detect(self, image: np.ndarray) -> list[PlateResult]:
        if not self.loaded:
            raise RuntimeError("Pipeline not loaded, call load() first")

        cfg = self.settings
        h, w = image.shape[:2]

        boxes = self.model(image, conf=cfg.model.confidence, verbose=False)[0].boxes
        plates = []
        for xyxy, conf in zip(boxes.xyxy.tolist(), boxes.conf.tolist()):
            x1, y1, x2, y2 = (int(v) for v in xyxy)

            pad_x = max(cfg.ocr.crop_padding, int((x2 - x1) * cfg.ocr.crop_padding_ratio))
            pad_y = max(cfg.ocr.crop_padding, int((y2 - y1) * cfg.ocr.crop_padding_ratio))
            crop = image[max(0, y1 - pad_y):min(h, y2 + pad_y), max(0, x1 - pad_x):min(w, x2 + pad_x)]
            if crop.size == 0:
                continue

            read = self.read_text(crop)
            needs_review = (not read.valid
                            or read.confidence < cfg.ocr.min_confidence
                            or read.fixes > cfg.ocr.max_fixes)
            log.info("Plate box conf %.2f: raw %r -> %r (valid=%s, review=%s)",
                     conf, read.raw, read.text, read.valid, needs_review)

            plates.append(PlateResult(
                box=(x1, y1, x2, y2),
                det_conf=round(conf, 4),
                text=read.text,
                raw_text=read.raw,
                ocr_conf=round(read.confidence, 4),
                valid=read.valid,
                format=read.format,
                needs_review=needs_review,
                crop=crop,
            ))

        return plates
