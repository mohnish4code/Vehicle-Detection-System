import numpy as np

import pytest

from app.config import Settings
from app.pipeline import PlatePipeline, ocr_scale, preprocess_variants


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
