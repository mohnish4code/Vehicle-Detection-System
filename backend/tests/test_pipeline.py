import numpy as np

from app.config import Settings
from app.pipeline import PlatePipeline


class FakeReader:
    def __init__(self, reads):
        self.reads = reads
        self.calls = 0

    def readtext(self, img, **kwargs):
        text, prob = self.reads[min(self.calls, len(self.reads) - 1)]
        self.calls += 1
        return [([[0, 0], [100, 0], [100, 30], [0, 30]], text, prob)]


def pipeline_with(reads):
    pipe = PlatePipeline(Settings())
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
