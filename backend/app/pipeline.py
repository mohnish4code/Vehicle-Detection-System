"""Plate detection + OCR pipeline shared by the CLI and the web app."""

import logging
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from statistics import median

import cv2
import numpy as np

from .config import Settings, get_settings
from .decoding import decode_plate, greedy
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


def ocr_scale(crop: np.ndarray, target_height: int, upscale: float) -> float:
    """How much to resize a crop before OCR.

    With target_height set, every crop is brought to roughly that height, so tiny
    plates are enlarged enough to read and big ones from phone photos are shrunk
    (faster, and EasyOCR doesn't need more). 0 means always use `upscale`.
    """
    if not target_height:
        return upscale
    return float(np.clip(target_height / crop.shape[0], 0.25, 8.0))


def preprocess_variants(crop: np.ndarray, scale: float = 2) -> list[np.ndarray]:
    """A few versions of the crop; different ones work better on different plates."""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    interp = cv2.INTER_CUBIC if scale >= 1 else cv2.INTER_AREA
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=interp)

    # local contrast, good for shiny or unevenly lit plates
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4)).apply(gray)
    # threshold window grows with the image so it stays about a character wide
    block = max(11, (gray.shape[0] // 6) | 1)
    adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, 5)
    _, otsu = cv2.threshold(cv2.GaussianBlur(gray, (5, 5), 0), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    return [gray, clahe, adaptive, otsu]


VARIANT_NAMES = ("gray", "clahe", "adaptive", "otsu")


def _text_boxes(ocr_results, ignore_words) -> list[dict]:
    """(bbox, text, prob[, probs]) tuples -> dicts with position, minus empty / ignored text."""
    ignore = {w.upper() for w in ignore_words}
    items = []
    for bbox, text, prob, *extra in ocr_results:
        text = normalize(text)
        if not text or text in ignore:
            continue
        ys = [p[1] for p in bbox]
        xs = [p[0] for p in bbox]
        items.append({
            "text": text,
            "prob": float(prob),
            "probs": extra[0] if extra else None,
            "cy": (min(ys) + max(ys)) / 2,
            "h": max(ys) - min(ys),
            "x": min(xs),
        })
    return items


def _rows(items: list[dict]) -> list[list[dict]]:
    """Group text boxes into rows, top to bottom, each row left to right."""
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
    for row in rows:
        row.sort(key=lambda i: i["x"])
    return rows


def group_rows(ocr_results, ignore_words=("IND",)) -> list[tuple[str, float]]:
    """Group EasyOCR boxes into text rows, top to bottom.

    ocr_results is EasyOCR's list of (bbox, text, prob). Returns one
    (text, confidence) per row, with boxes in a row read left to right.
    """
    out = []
    for row in _rows(_text_boxes(ocr_results, ignore_words)):
        text = "".join(i["text"] for i in row)
        conf = sum(i["prob"] * len(i["text"]) for i in row) / len(text)
        out.append((text, conf))
    return out


def decode_rows(rows: list[list[dict]], alphabet: str) -> OcrRead | None:
    """Plate-aware decoding over the character probabilities of each run of consecutive rows."""
    candidates = []
    for start in range(len(rows)):
        for end in range(start + 1, len(rows) + 1):
            boxes = [b for row in rows[start:end] for b in row]
            raw = "".join(b["text"] for b in boxes)
            # one blank frame between boxes so their characters don't merge
            sep = np.zeros((1, len(alphabet) + 1))
            sep[0, 0] = 1.0
            parts = []
            for b in boxes:
                parts += [b["probs"], sep]
            found = decode_plate(np.concatenate(parts[:-1]), alphabet)
            # EasyOCR's own per-character confidence for these boxes. The decoded text's
            # probability alone can be high even when a character was misread (a 4 read
            # confidently as G still fits a plate), so report the more cautious of the two.
            ocr_conf = sum(b["prob"] * len(b["text"]) for b in boxes) / len(raw)
            if found:
                d = found[0]
                conf = min(ocr_conf, d.confidence)
                candidates.append(OcrRead(d.text, conf, True, d.format, raw, edit_distance(raw, d.text)))
            else:
                candidates.append(OcrRead(raw, ocr_conf, False, None, raw))
    return max(candidates, key=read_rank) if candidates else None


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


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


def pick_read(reads: list[OcrRead]) -> OcrRead:
    """Best read across the preprocessing variants.

    Valid plates win; among those the text most variants agree on, then the most
    confident. (Preferring the longest text instead let decoded reads with an
    extra character win - measured with scripts/evaluate.py.)
    """
    valid = [r for r in reads if r.valid]
    if valid:
        votes = Counter(r.text for r in valid)
        return max(valid, key=lambda r: (votes[r.text], r.confidence, -r.fixes))
    return max(reads, key=read_rank) if reads else OcrRead("", 0.0)


def charset_map(charset: list[str]) -> np.ndarray:
    """Matrix taking a recognizer's output columns (index 0 = CTC blank) to blank + PLATE_CHARS.

    Lowercase letters count towards their uppercase letter; everything else is dropped.
    """
    index = {ch: i for i, ch in enumerate(charset)}
    out = np.zeros((len(charset), len(PLATE_CHARS) + 1), np.float32)
    out[0, 0] = 1
    for i, ch in enumerate(PLATE_CHARS, 1):
        for variant in {ch, ch.lower()}:
            if variant in index:
                out[index[variant], i] = 1
    return out


def read_variants(variant_ocr, ocr) -> tuple[OcrRead, list[OcrRead]]:
    """Decode each variant's OCR boxes, stopping early on a confident read.

    variant_ocr yields (name, OCR boxes) per engine and variant; ocr is the
    [ocr] settings. Returns the chosen read and every variant's read.
    """
    reads = []
    for _, boxes in variant_ocr:
        if ocr.decoder == "constrained":
            read = decode_rows(_rows(_text_boxes(boxes, ocr.ignore_words)), PLATE_CHARS)
        else:
            read = best_read(group_rows(boxes, ocr.ignore_words))
        if not read:
            continue
        log.debug("OCR variant read %r -> %r (conf %.2f)", read.raw, read.text, read.confidence)
        reads.append(read)
        if read.valid and read.fixes == 0 and read.confidence >= ocr.early_stop_confidence:
            break
    return pick_read(reads), reads


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
        self.paddle = None
        self.error: str | None = None
        self._cols: list[int] | None = None
        self.last_reads: list[OcrRead] = []
        # YOLO and EasyOCR aren't safe to call from several threads at once
        self._lock = threading.Lock()

    def load(self):
        """Load YOLO and the OCR engines. Slow, so do it once and reuse the pipeline."""
        from ultralytics import YOLO

        weights = self.settings.path(self.settings.model.weights)
        if not weights.exists():
            raise FileNotFoundError(f"Model weights not found at {weights}")

        start = time.perf_counter()
        self.model = YOLO(str(weights))
        self.load_ocr()
        log.info("Loaded model %s and OCR %s in %.1fs", weights.name, self.settings.ocr.engines,
                 time.perf_counter() - start)
        return self

    def load_ocr(self):
        ocr = self.settings.ocr
        if "easyocr" in ocr.engines and self.reader is None:
            import easyocr
            self.reader = easyocr.Reader(ocr.languages, gpu=ocr.gpu, verbose=False)
        if "paddle" in ocr.engines and self.paddle is None:
            from rapidocr_onnxruntime import RapidOCR
            self.paddle = RapidOCR()
            self._paddle_map = charset_map(self.paddle.text_rec.postprocess_op.character)
        return self

    @property
    def loaded(self) -> bool:
        engines = self.settings.ocr.engines
        return (self.model is not None
                and ("easyocr" not in engines or self.reader is not None)
                and ("paddle" not in engines or self.paddle is not None))

    def _char_probs(self, line: np.ndarray) -> np.ndarray | None:
        """Recognizer output for one text line (already 64 px high): frames x (blank + PLATE_CHARS)."""
        import torch

        if line.shape[1] < 8:
            return None
        if self._cols is None:
            chars = self.reader.converter.character  # index 0 is the CTC blank
            self._cols = [0] + [chars.index(c) for c in PLATE_CHARS]

        x = torch.from_numpy(line.astype(np.float32) / 255.0).sub_(0.5).div_(0.5)
        with torch.no_grad():
            preds = self.reader.recognizer(x[None, None].to(self.reader.device), None)
        probs = torch.softmax(preds[0], dim=-1).cpu().numpy()[:, self._cols]
        return probs / probs.sum(axis=1, keepdims=True)

    def _ocr_boxes(self, img: np.ndarray) -> list[tuple]:
        """Like reader.readtext, but also returns each box's character probabilities."""
        from easyocr.recognition import custom_mean
        from easyocr.utils import get_image_list

        horizontal, free = self.reader.detect(img)
        lines, _ = get_image_list(horizontal[0], free[0], img, model_height=64)
        out = []
        for quad, line in lines:
            probs = self._char_probs(line)
            if probs is None:
                continue
            best = probs.argmax(axis=1)
            peaks = probs.max(axis=1)[best != 0]
            out.append((quad, greedy(probs, PLATE_CHARS), custom_mean(peaks) if len(peaks) else 0.0, probs))
        return out

    def _paddle_boxes(self, img: np.ndarray) -> list[tuple]:
        """Same output as _ocr_boxes, from RapidOCR's PP-OCR text detector and recognizer."""
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        boxes, _ = self.paddle.auto_text_det(img)
        if boxes is None:
            return []
        rec = self.paddle.text_rec
        _, rec_h, rec_w = rec.rec_image_shape
        out = []
        for quad, line in zip(boxes, self.paddle.get_crop_img_list(img, boxes), strict=True):
            h, w = line.shape[:2]
            if w < 8 or h < 4:
                continue
            x = rec.resize_norm_img(line, max(rec_w / rec_h, w / h))[None].astype(np.float32)
            probs = rec.session(x)[0][0] @ self._paddle_map
            probs /= probs.sum(axis=1, keepdims=True)
            # drop the frames that only cover the right-hand padding
            probs = probs[:max(1, int(np.ceil(probs.shape[0] * min(1.0, (w / h) / (x.shape[3] / rec_h)))))]
            best = probs.argmax(axis=1)
            peaks = probs.max(axis=1)[best != 0]
            out.append((quad.tolist(), greedy(probs, PLATE_CHARS), float(np.mean(peaks)) if len(peaks) else 0.0,
                        probs))
        return out

    def variant_ocr(self, crop: np.ndarray):
        """OCR output for each engine and preprocessing variant, computed lazily (so early stopping saves time).

        Yields (name, boxes). PaddleOCR reads the colour crop and the contrast-enhanced one;
        EasyOCR reads all four variants from preprocess_variants.
        """
        ocr = self.settings.ocr
        scale = ocr_scale(crop, ocr.target_height, ocr.upscale)
        for engine in ocr.engines:
            if engine == "paddle":
                interp = cv2.INTER_CUBIC if scale >= 1 else cv2.INTER_AREA
                color = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=interp)
                yield "paddle:color", self._paddle_boxes(color)
                yield "paddle:clahe", self._paddle_boxes(preprocess_variants(crop, scale)[1])
            elif engine == "easyocr":
                for name, variant in zip(VARIANT_NAMES, preprocess_variants(crop, scale), strict=True):
                    if ocr.decoder == "constrained":
                        yield f"easyocr:{name}", self._ocr_boxes(variant)
                    else:
                        yield f"easyocr:{name}", self.reader.readtext(variant, allowlist=PLATE_CHARS)
            else:
                raise ValueError(f"Unknown OCR engine {engine!r}")

    def read_text(self, crop: np.ndarray) -> OcrRead:
        read, self.last_reads = read_variants(self.variant_ocr(crop), self.settings.ocr)
        return read

    def detect(self, image: np.ndarray) -> list[PlateResult]:
        if not self.loaded:
            raise RuntimeError("Pipeline not loaded, call load() first")

        with self._lock:
            return self._detect(image)

    def crop_plate(self, image: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
        """Cut the plate out with some margin; YOLO boxes often clip the edge characters."""
        ocr = self.settings.ocr
        h, w = image.shape[:2]
        x1, y1, x2, y2 = box
        pad_x = max(ocr.crop_padding, int((x2 - x1) * ocr.crop_padding_ratio))
        pad_y = max(ocr.crop_padding, int((y2 - y1) * ocr.crop_padding_ratio))
        return image[max(0, y1 - pad_y):min(h, y2 + pad_y), max(0, x1 - pad_x):min(w, x2 + pad_x)]

    def needs_review(self, read: OcrRead) -> bool:
        ocr = self.settings.ocr
        return not read.valid or read.confidence < ocr.min_confidence or read.fixes > ocr.max_fixes

    def _detect(self, image: np.ndarray) -> list[PlateResult]:
        cfg = self.settings

        boxes = self.model(image, conf=cfg.model.confidence, verbose=False)[0].boxes
        plates = []
        for xyxy, conf in zip(boxes.xyxy.tolist(), boxes.conf.tolist(), strict=True):
            x1, y1, x2, y2 = (int(v) for v in xyxy)
            crop = self.crop_plate(image, (x1, y1, x2, y2))
            if crop.size == 0:
                continue

            read = self.read_text(crop)
            needs_review = self.needs_review(read)
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
