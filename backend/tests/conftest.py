import cv2
import gspread
import numpy as np
import pytest

from app.config import Settings
from app.pipeline import PlateResult
from app.sheets import SheetsLog


class FakeResponse:
    def __init__(self, code):
        self.status_code = code
        self.text = ""

    def json(self):
        return {"error": {"code": self.status_code, "message": "fake error", "status": "FAKE"}}


def api_error(code: int) -> gspread.exceptions.APIError:
    return gspread.exceptions.APIError(FakeResponse(code))


class FakeWorksheet:
    """Just enough of gspread.Worksheet. Put exceptions in .fail to make the next calls raise."""

    def __init__(self, rows=None):
        self.rows = [list(r) for r in rows or []]
        self.fail: list[Exception] = []
        self.calls = 0

    def _tick(self):
        self.calls += 1
        if self.fail:
            raise self.fail.pop(0)

    def row_values(self, n):
        self._tick()
        return list(self.rows[n - 1]) if len(self.rows) >= n else []

    def get_all_values(self):
        self._tick()
        return [list(r) for r in self.rows]

    def append_row(self, values):
        self._tick()
        self.rows.append(["" if v is None else str(v) for v in values])


class FakePipeline:
    def __init__(self, results=None, loaded=True, error=None):
        # results: list of plate lists, one per detect() call (last one repeats)
        self.results = results if results is not None else [[make_plate()]]
        self.loaded = loaded
        self.error = error
        self.calls = 0

    def detect(self, image):
        out = self.results[min(self.calls, len(self.results) - 1)]
        self.calls += 1
        if isinstance(out, Exception):
            raise out
        return out


def make_plate(text="MH12DE1433", valid=True, needs_review=False, fmt="standard", ocr_conf=0.9):
    return PlateResult(
        box=(10, 20, 110, 60),
        det_conf=0.91,
        text=text,
        raw_text=text,
        ocr_conf=ocr_conf,
        valid=valid,
        format=fmt if valid else None,
        needs_review=needs_review,
        crop=np.full((40, 100, 3), 255, np.uint8),
    )


def image_bytes(ext=".jpg", size=(120, 200), noise=False) -> bytes:
    shape = (*size, 3)
    img = np.random.default_rng(0).integers(0, 255, shape, np.uint8) if noise else np.zeros(shape, np.uint8)
    ok, buf = cv2.imencode(ext, img)
    assert ok
    return buf.tobytes()


@pytest.fixture
def settings(tmp_path, monkeypatch):
    # Never pick up a real key from secrets/ or the environment in tests
    monkeypatch.delenv("GOOGLE_CREDENTIALS", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    s = Settings()
    s.sheets.spreadsheet_id = "test-sheet"
    s.sheets.credentials_file = str(tmp_path / "missing-key.json")
    s.sheets.retry_base_seconds = 0
    s.sheets.cache_seconds = 0
    return s


def not_configured(settings):
    settings.sheets.spreadsheet_id = ""
    settings.sheets.spreadsheet_name = ""
    return settings


@pytest.fixture
def worksheet():
    return FakeWorksheet()


@pytest.fixture
def sleeps():
    return []


@pytest.fixture
def sheets(settings, worksheet, sleeps):
    return SheetsLog(settings, opener=lambda s: worksheet, sleep=sleeps.append)
