import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.sheets import HEADER, SheetsLog

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
    settings.sheets.spreadsheet_id = ""
    pipe = FakePipeline(loaded=False, error="Model file not found (models/best.pt).")
    with TestClient(create_app(settings, pipe, SheetsLog(settings))) as c:
        body = c.get("/api/health").json()
    assert body["status"] == "degraded"
    assert body["model"] == {"ok": False, "error": "Model file not found (models/best.pt)."}
    assert body["sheets"]["ok"] is False
    assert "spreadsheet_id" in body["sheets"]["error"]


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


def test_detect_bad_image_does_not_fail_batch(client):
    files = [("files", ("broken.jpg", b"not really a jpeg", "image/jpeg"))] + upload("car.jpg")
    res = client.post("/api/detect", files=files)
    assert res.status_code == 200
    statuses = [r["status"] for r in res.json()["results"]]
    assert statuses == ["bad_image", "ok"]


def test_detect_without_files(client):
    assert_error(client.post("/api/detect"), 422, "VALIDATION_ERROR")


def test_detect_when_model_missing(settings, sheets):
    pipe = FakePipeline(loaded=False, error="Model file not found (models/best.pt).")
    with TestClient(create_app(settings, pipe, sheets)) as c:
        err = assert_error(c.post("/api/detect", files=upload("car.jpg")), 503, "MODEL_UNAVAILABLE")
    assert "best.pt" in err["message"]


def test_unexpected_error_hides_details(settings, sheets):
    pipe = FakePipeline([RuntimeError("secret internal detail")])
    with TestClient(create_app(settings, pipe, sheets), raise_server_exceptions=False) as c:
        res = c.post("/api/detect", files=upload("car.jpg"))
    assert_error(res, 500, "INTERNAL_ERROR")
    assert "secret" not in res.text


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
    settings.sheets.spreadsheet_id = ""
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
