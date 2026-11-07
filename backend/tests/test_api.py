import threading

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.pipeline import PipelinePool
from app.sheets import HEADER, SheetsLog

from .conftest import FakePipeline, api_error, image_bytes, make_plate


@pytest.fixture
def pipeline():
    return FakePipeline()


@pytest.fixture
def client(settings, pipeline, sheets):
    with TestClient(create_app(settings, pipeline, sheets)) as c:
        yield c


def upload(*names):
    return [("files", (n, image_bytes(), "image/jpeg")) for n in names]


def assert_error(res, status, code):
    assert res.status_code == status, res.text
    body = res.json()
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    assert "Traceback" not in res.text
    return body["error"]


# -- health --

def test_health_ok(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "model": {"ok": True, "error": None},
                          "sheets": {"ok": True, "error": None}}


def test_health_degraded_without_model_or_sheets(settings):
    pipe = FakePipeline(loaded=False, error="Model file not found (models/best.pt).")
    with TestClient(create_app(settings, pipe, SheetsLog(settings))) as c:
        body = c.get("/api/health").json()
    assert body["status"] == "degraded"
    assert body["model"] == {"ok": False, "error": "Model file not found (models/best.pt)."}
    assert body["sheets"]["ok"] is False
    assert "service account key" in body["sheets"]["error"]


# -- detect --

def test_detect_returns_plates(client):
    res = client.post("/api/detect", files=upload("car.jpg"))
    assert res.status_code == 200, res.text
    result = res.json()["results"][0]
    assert result["filename"] == "car.jpg"
    assert result["status"] == "ok"
    assert (result["width"], result["height"]) == (200, 120)

    plate = result["plates"][0]
    assert plate["text"] == "MH12DE1433"
    assert plate["box"] == {"x1": 10, "y1": 20, "x2": 110, "y2": 60}
    assert plate["det_conf"] == 0.91 and plate["ocr_conf"] == 0.9
    assert plate["valid"] is True and plate["needs_review"] is False
    assert plate["format"] == "standard"
    assert plate["crop"].startswith("data:image/jpeg;base64,")


def test_detect_multiple_images_with_mixed_results(settings, sheets):
    pipe = FakePipeline([
        [make_plate()],
        [],
        [make_plate(text="", valid=False, needs_review=True, ocr_conf=0)],
        [make_plate(text="XQ7", valid=False, needs_review=True)],
    ])
    with TestClient(create_app(settings, pipe, sheets)) as c:
        res = c.post("/api/detect", files=upload("a.jpg", "b.jpg", "c.jpg", "d.jpg"))

    results = res.json()["results"]
    assert [r["status"] for r in results] == ["ok", "no_plate", "unreadable", "invalid_format"]
    assert results[0]["message"] is None
    assert "No number plate found" in results[1]["message"]
    assert results[2]["message"] == "Plate found but text unclear - try a closer, sharper photo."
    assert res.json()["total_ms"] >= 0


def test_detect_bad_files_do_not_fail_batch(client):
    files = [
        ("files", ("broken.jpg", image_bytes()[:60], "image/jpeg")),       # truncated jpeg
        ("files", ("notes.jpg", b"definitely not an image", "image/jpeg")),
        ("files", ("empty.png", b"", "image/png")),
        ("files", ("anim.gif", b"GIF89a" + b"\0" * 50, "image/gif")),
        ("files", ("IMG_0001.HEIC", b"\0\0\0\x18ftypheic" + b"\0" * 50, "image/heic")),
        ("files", ("tiny.png", image_bytes(".png", (20, 20)), "image/png")),
    ] + upload("car.jpg")
    res = client.post("/api/detect", files=files)
    assert res.status_code == 200

    results = {r["filename"]: r for r in res.json()["results"]}
    assert results["broken.jpg"]["status"] == "bad_image"
    assert "damaged" in results["broken.jpg"]["message"]
    assert results["notes.jpg"]["status"] == "unsupported_type"
    assert results["empty.png"]["message"] == "The file is empty."
    assert results["anim.gif"]["status"] == "unsupported_type"
    assert results["IMG_0001.HEIC"]["status"] == "bad_image"  # HEIC header, but no picture in it
    assert "too small" in results["tiny.png"]["message"]
    assert results["car.jpg"]["status"] == "ok"


def test_detect_type_comes_from_content_not_name(client):
    # a PNG named .jpg and sent as octet-stream is still fine
    files = [("files", ("photo.jpg", image_bytes(".png"), "application/octet-stream"))]
    assert client.post("/api/detect", files=files).json()["results"][0]["status"] == "ok"


def test_detect_file_too_large(settings, pipeline, sheets):
    settings.api.max_file_mb = 0.0005  # ~500 bytes
    with TestClient(create_app(settings, pipeline, sheets)) as c:
        files = [("files", ("big.png", image_bytes(".png", (300, 300), noise=True), "image/png"))]
        result = c.post("/api/detect", files=files).json()["results"][0]
    assert result["status"] == "too_large"
    assert "MB" in result["message"]


def test_detect_too_many_pixels(settings, pipeline, sheets):
    settings.api.max_image_megapixels = 0.01
    with TestClient(create_app(settings, pipeline, sheets)) as c:
        result = c.post("/api/detect", files=upload("car.jpg")).json()["results"][0]
    assert result["status"] == "too_large"
    assert "200x120" in result["message"]


def test_detect_too_many_files(settings, pipeline, sheets):
    settings.api.max_files = 2
    with TestClient(create_app(settings, pipeline, sheets)) as c:
        err = assert_error(c.post("/api/detect", files=upload("a.jpg", "b.jpg", "c.jpg")), 400, "TOO_MANY_FILES")
    assert "at most 2" in err["message"]
    assert pipeline.calls == 0


def test_request_body_too_large(settings, pipeline, sheets):
    settings.api.max_files = 1
    settings.api.max_file_mb = 0.01
    with TestClient(create_app(settings, pipeline, sheets)) as c:
        files = [("files", ("huge.jpg", b"\xff\xd8\xff" + b"\0" * 2_000_000, "image/jpeg"))]
        assert_error(c.post("/api/detect", files=files), 413, "PAYLOAD_TOO_LARGE")
    assert pipeline.calls == 0


def test_detect_without_files(client):
    err = assert_error(client.post("/api/detect"), 422, "VALIDATION_ERROR")
    assert err["details"][0]["field"] == "files"


def test_detect_when_model_missing(settings, sheets):
    pipe = FakePipeline(loaded=False, error="Model file not found (models/best.pt).")
    with TestClient(create_app(settings, pipe, sheets)) as c:
        err = assert_error(c.post("/api/detect", files=upload("car.jpg")), 503, "MODEL_UNAVAILABLE")
    assert "best.pt" in err["message"]


def test_detection_crash_only_fails_that_image(settings, sheets):
    pipe = FakePipeline([RuntimeError("secret internal detail"), [make_plate()]])
    with TestClient(create_app(settings, pipe, sheets)) as c:
        res = c.post("/api/detect", files=upload("a.jpg", "b.jpg"))
    assert res.status_code == 200
    assert [r["status"] for r in res.json()["results"]] == ["error", "ok"]
    assert "secret" not in res.text and "Traceback" not in res.text


def test_unexpected_error_hides_details(client, sheets, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(sheets, "recent", boom)
    res = client.get("/api/logs", headers={"Origin": "http://localhost:5173"})
    assert_error(res, 500, "INTERNAL_ERROR")
    assert "secret" not in res.text
    # still readable by the frontend
    assert res.headers["access-control-allow-origin"] == "http://localhost:5173"


# -- CORS --

def test_cors_allows_frontend(client):
    res = client.options("/api/detect", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert client.get("/api/health", headers={"Origin": "http://localhost:5173"}) \
        .headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_blocks_other_origins(client):
    res = client.options("/api/detect", headers={
        "Origin": "https://evil.example.com", "Access-Control-Request-Method": "POST"})
    assert res.status_code == 400
    assert "access-control-allow-origin" not in res.headers
    res = client.get("/api/health", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in res.headers


def test_cors_rejects_disallowed_method(client):
    res = client.options("/api/logs", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "DELETE"})
    assert res.status_code == 400


# -- logs --

def test_save_log(client, worksheet):
    res = client.post("/api/logs", json={"plate": "mh 12 de 1433", "source": "camera",
                                         "det_conf": 0.91, "ocr_conf": 0.8})
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["plate"] == "MH12DE1433"
    assert body["format"] == "standard"
    assert worksheet.rows[0] == HEADER
    assert worksheet.rows[1][0] == "MH12DE1433"
    assert worksheet.rows[1][2:] == ["camera", "0.91", "0.8", "standard"]


def test_save_bh_plate(client):
    res = client.post("/api/logs", json={"plate": "22BH6517A"})
    assert res.json()["format"] == "bh"
    assert res.json()["source"] == "upload"


def test_save_duplicate_rejected(client, worksheet):
    client.post("/api/logs", json={"plate": "MH12DE1433"})
    err = assert_error(client.post("/api/logs", json={"plate": "MH12DE1433"}), 409, "DUPLICATE_PLATE")
    assert "already logged" in err["message"]
    assert len(worksheet.rows) == 2  # header + one row


def test_save_invalid_plate(client, worksheet):
    err = assert_error(client.post("/api/logs", json={"plate": "HELLO123"}), 422, "INVALID_PLATE")
    assert "HELLO123" in err["message"]
    assert worksheet.rows == []


def test_save_bad_body(client):
    assert_error(client.post("/api/logs", json={"plate": "MH12DE1433", "ocr_conf": 5}), 422, "VALIDATION_ERROR")
    assert_error(client.post("/api/logs", json={"plate": "MH12DE1433", "source": "fax"}), 422, "VALIDATION_ERROR")


def test_save_when_sheets_down(client, sheets, worksheet, settings):
    sheets.connect()
    worksheet.fail = [api_error(503)] * (settings.sheets.retries + 2)
    err = assert_error(client.post("/api/logs", json={"plate": "MH12DE1433"}), 503, "SHEETS_UNAVAILABLE")
    assert "Google Sheets" in err["message"]


def test_save_when_sheets_not_configured(settings, pipeline):
    # settings point at a key file that doesn't exist
    with TestClient(create_app(settings, pipeline, SheetsLog(settings))) as c:
        assert_error(c.post("/api/logs", json={"plate": "MH12DE1433"}), 503, "SHEETS_NOT_CONFIGURED")
        # detection still works without Sheets
        assert c.post("/api/detect", files=upload("car.jpg")).status_code == 200


def test_list_logs_with_search(client):
    for plate in ("MH12DE1433", "DL3CAB1234", "22BH6517A"):
        client.post("/api/logs", json={"plate": plate})

    body = client.get("/api/logs").json()
    assert body["total"] == 3
    assert [i["plate"] for i in body["items"]] == ["22BH6517A", "DL3CAB1234", "MH12DE1433"]

    assert [i["plate"] for i in client.get("/api/logs", params={"q": "dl3"}).json()["items"]] == ["DL3CAB1234"]
    assert client.get("/api/logs", params={"format": "bh"}).json()["total"] == 1
    assert_error(client.get("/api/logs", params={"limit": 0}), 422, "VALIDATION_ERROR")


def test_unknown_route(client):
    assert_error(client.get("/api/nope"), 404, "NOT_FOUND")


# -- several pipeline instances --

class BlockingPipeline(FakePipeline):
    """detect() waits until `parties` calls are inside it at once, so it only passes if they run in parallel."""

    def __init__(self, barrier):
        super().__init__()
        self.barrier = barrier

    def detect(self, image):
        self.barrier.wait(timeout=5)
        return super().detect(image)


def test_images_of_one_request_run_on_all_pipelines(settings, sheets):
    barrier = threading.Barrier(2)
    pool = PipelinePool([BlockingPipeline(barrier), BlockingPipeline(barrier)])
    with TestClient(create_app(settings, pool, sheets)) as c:
        res = c.post("/api/detect", files=upload("a.jpg", "b.jpg"))
    assert res.status_code == 200
    assert [r["status"] for r in res.json()["results"]] == ["ok", "ok"]
    assert [p.calls for p in pool.pipelines] == [1, 1]


def test_pool_reports_first_error():
    pool = PipelinePool([FakePipeline(), FakePipeline(loaded=False, error="boom")])
    assert not pool.loaded
    assert pool.error == "boom"


def heic_bytes(size=(120, 200)) -> bytes:
    import io

    import pillow_heif

    h, w = size
    img = np.zeros((h, w, 3), np.uint8)
    img[:, : w // 2] = (255, 0, 0)  # left half red
    heif = pillow_heif.from_bytes(mode="RGB", size=(w, h), data=img.tobytes())
    buf = io.BytesIO()
    heif.save(buf, quality=90)
    return buf.getvalue()


def test_heic_photo_is_decoded(client, pipeline):
    files = [("files", ("IMG_0002.HEIC", heic_bytes(), "image/heic"))]
    result = client.post("/api/detect", files=files).json()["results"][0]
    assert result["status"] == "ok"
    assert (result["width"], result["height"]) == (200, 120)


def test_heic_colours_come_out_as_bgr():
    from app.api.uploads import decode_heic

    img = decode_heic(heic_bytes())
    assert img[0, 0, 2] > 200 and img[0, 0, 0] < 50  # red is the last channel in OpenCV's BGR
