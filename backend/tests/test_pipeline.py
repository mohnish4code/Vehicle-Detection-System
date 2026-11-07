import numpy as np

import pytest

from app.config import Settings
from app.pipeline import PLATE_CHARS, PlatePipeline, charset_map, ocr_scale, preprocess_variants


class FakeReader:
    def __init__(self, reads):
        self.reads = reads
        self.calls = 0

    def readtext(self, img, **kwargs):
        text, prob = self.reads[min(self.calls, len(self.reads) - 1)]
        self.calls += 1
        return [([[0, 0], [100, 0], [100, 30], [0, 30]], text, prob)]


def pipeline_with(reads):
    settings = Settings()
    settings.ocr.engines = ["easyocr"]
    settings.ocr.decoder = "classic"  # FakeReader only mimics readtext()
    pipe = PlatePipeline(settings)
    pipe.reader = FakeReader(reads)
    return pipe


CROP = np.full((40, 120, 3), 200, np.uint8)


def test_stops_after_confident_read():
    pipe = pipeline_with([("22BH6517A", 0.98)])
    read = pipe.read_text(CROP)
    assert read.text == "22BH6517A"
    assert pipe.reader.calls == 1


def test_keeps_going_when_read_needed_fixes():
    pipe = pipeline_with([("MHI2DE1433", 0.95)])
    pipe.read_text(CROP)
    assert pipe.reader.calls == 4


def test_keeps_going_when_not_confident():
    pipe = pipeline_with([("MH12DE1433", 0.7), ("MH12DE1433", 0.95)])
    read = pipe.read_text(CROP)
    assert pipe.reader.calls == 2
    assert read.confidence == 0.95


def test_early_stop_can_be_disabled():
    pipe = pipeline_with([("22BH6517A", 0.98)])
    pipe.settings.ocr.early_stop_confidence = 1.1
    pipe.read_text(CROP)
    assert pipe.reader.calls == 4


@pytest.mark.parametrize("height, expected", [(25, 4.0), (100, 1.0), (400, 0.25), (5, 8.0)])
def test_crops_scaled_to_target_height(height, expected):
    crop = np.zeros((height, height * 4, 3), np.uint8)
    assert ocr_scale(crop, 100, 2) == expected


def test_fixed_upscale_when_no_target():
    assert ocr_scale(np.zeros((25, 100, 3), np.uint8), 0, 2) == 2


def test_variants_have_the_scaled_size():
    variants = preprocess_variants(np.full((25, 100, 3), 128, np.uint8), 4)
    assert len(variants) == 4
    assert all(v.shape == (100, 400) for v in variants)


def test_crop_padding_scales_with_plate():
    settings = Settings()
    settings.ocr.crop_padding = 4
    pipe = PlatePipeline(settings)
    image = np.zeros((500, 500, 3), np.uint8)
    # small far-away plate: margin stays small instead of a fixed 25px
    assert pipe.crop_plate(image, (100, 100, 160, 115)).shape[:2] == (23, 78)


CHARSET = ["blank", *"abcdefghijklmnopqrstuvwxyz", *PLATE_CHARS, "京", "-"]


class FakeRecognizer:
    """Mimics RapidOCR's text_rec: emits each character of `text` followed by a blank frame."""
    rec_image_shape = [3, 48, 320]

    def __init__(self, text):
        self.text = text
        self.postprocess_op = type("Post", (), {"character": CHARSET})()

    def resize_norm_img(self, img, max_wh_ratio):
        return np.zeros((3, 48, int(48 * max_wh_ratio)), np.float32)

    def session(self, x):
        frames = x.shape[3] // 8
        probs = np.zeros((frames, len(CHARSET)), np.float32)
        probs[:, 0] = 1
        for i, ch in enumerate(self.text):
            probs[2 * i] = 0
            probs[2 * i, CHARSET.index(ch)] = 1
        return [probs[None]]


class FakePaddle:
    def __init__(self, text):
        self.text_rec = FakeRecognizer(text)

    def auto_text_det(self, img):
        return [np.array([[0, 0], [400, 0], [400, 40], [0, 40]], np.float32)], 0.0

    def get_crop_img_list(self, img, boxes):
        return [np.zeros((40, 400, 3), np.uint8)]


def paddle_pipeline(text):
    settings = Settings()
    settings.ocr.engines = ["paddle"]
    pipe = PlatePipeline(settings)
    pipe.paddle = FakePaddle(text)
    pipe._paddle_map = charset_map(CHARSET)
    return pipe


def test_charset_map_folds_lowercase_and_drops_other_chars():
    m = charset_map(CHARSET)
    assert m.shape == (len(CHARSET), len(PLATE_CHARS) + 1)
    assert m[CHARSET.index("h"), PLATE_CHARS.index("H") + 1] == 1
    assert m[CHARSET.index("H"), PLATE_CHARS.index("H") + 1] == 1
    assert m[CHARSET.index("京")].sum() == 0


def test_paddle_engine_feeds_the_plate_decoder():
    # lowercase "h" from the recognizer still reads as H
    read = paddle_pipeline("Mh12DE1433").read_text(CROP)
    assert read.text == "MH12DE1433" and read.valid
