from datetime import datetime, timedelta

import pytest
import requests

from src.sheets import HEADER, IST, TIME_FORMAT, DuplicatePlate, SheetsError, SheetsLog

from .conftest import FakeWorksheet, api_error


def ago(minutes):
    return (datetime.now(IST) - timedelta(minutes=minutes)).strftime(TIME_FORMAT)


def test_header_added_to_empty_sheet(sheets, worksheet):
    sheets.connect()
    assert worksheet.rows == [HEADER]


def test_header_not_added_twice(settings):
    ws = FakeWorksheet([HEADER, ["MH12DE1433", ago(100), "upload", "0.9", "0.8", "standard"]])
    SheetsLog(settings, opener=lambda s: ws).connect()
    assert len(ws.rows) == 2


def test_reads_old_rows_without_header(settings):
    # rows written by the old streamlit app: plate, time, source
    ws = FakeWorksheet([["MH12DE1433", "2026-05-02 20:00:00", "streamlit_capture"]])
    log = SheetsLog(settings, opener=lambda s: ws)
    rows = log.entries()
    assert rows[0].plate == "MH12DE1433"
    assert rows[0].det_conf is None and rows[0].format is None


def test_add_writes_all_columns(sheets, worksheet):
    entry = sheets.add("KL07BZ4455", "camera", 0.91234, 0.8, "standard")
    row = worksheet.rows[-1]
    assert row[0] == "KL07BZ4455"
    assert datetime.strptime(row[1], TIME_FORMAT)  # IST timestamp
    assert row[2:] == ["camera", "0.9123", "0.8", "standard"]
    assert entry.timestamp == row[1]


def test_duplicate_within_window_rejected(sheets):
    sheets.add("MH12DE1433", "upload")
    with pytest.raises(DuplicatePlate) as exc:
        sheets.add("MH12DE1433", "upload")
    assert exc.value.status == 409
    assert "already logged" in exc.value.message


def test_duplicate_check_uses_rows_already_in_sheet(settings):
    # simulates a server restart: the earlier save is only in the sheet
    ws = FakeWorksheet([HEADER, ["MH12DE1433", ago(3), "upload", "", "", "standard"]])
    log = SheetsLog(settings, opener=lambda s: ws)
    with pytest.raises(DuplicatePlate):
        log.add("MH12DE1433", "upload")


def test_same_plate_allowed_after_window(settings):
    ws = FakeWorksheet([HEADER, ["MH12DE1433", ago(settings.sheets.dedupe_minutes + 1), "upload", "", "", ""]])
    SheetsLog(settings, opener=lambda s: ws).add("MH12DE1433", "upload")
    assert len(ws.rows) == 3


def test_different_plate_not_a_duplicate(sheets):
    sheets.add("MH12DE1433", "upload")
    sheets.add("DL3CAB1234", "upload")


def test_retries_on_quota_then_succeeds(sheets, worksheet, sleeps):
    sheets.connect()
    worksheet.fail = [api_error(429), api_error(503)]
    sheets.add("MH12DE1433", "upload")
    assert worksheet.rows[-1][0] == "MH12DE1433"
    assert len(sleeps) == 2


def test_quota_exhausted_gives_clear_error(sheets, worksheet, settings):
    sheets.connect()
    worksheet.fail = [api_error(429)] * (settings.sheets.retries + 1)
    with pytest.raises(SheetsError) as exc:
        sheets.entries(refresh=True)
    assert exc.value.code == "SHEETS_QUOTA"
    assert exc.value.status == 429


def test_permission_denied_not_retried(sheets, worksheet, sleeps):
    sheets.connect()
    worksheet.fail = [api_error(403)]
    with pytest.raises(SheetsError) as exc:
        sheets.add("MH12DE1433", "upload")
    assert exc.value.code == "SHEETS_PERMISSION"
    assert sleeps == []


def test_network_down(sheets, worksheet, settings):
    sheets.connect()
    worksheet.fail = [requests.ConnectionError("no route")] * (settings.sheets.retries + 1)
    with pytest.raises(SheetsError) as exc:
        sheets.add("MH12DE1433", "upload")
    assert exc.value.code == "SHEETS_UNAVAILABLE"
    assert "internet" in exc.value.message


def test_sheet_not_found_on_connect(settings):
    def opener(s):
        raise api_error(404)

    status = SheetsLog(settings, opener=opener).status()
    assert status["connected"] is False
    assert status["code"] == "SHEETS_NOT_FOUND"


def test_missing_credentials_reported_not_raised(settings, tmp_path, monkeypatch):
    monkeypatch.delenv("GOOGLE_CREDENTIALS", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    settings.sheets.credentials_file = str(tmp_path / "nope.json")

    status = SheetsLog(settings).status()  # real opener
    assert status == {"connected": False, "code": "SHEETS_NOT_CONFIGURED", "error": status["error"]}
    assert "service account key" in status["error"]


def test_missing_spreadsheet_id(settings):
    settings.sheets.spreadsheet_id = ""
    status = SheetsLog(settings).status()
    assert status["code"] == "SHEETS_NOT_CONFIGURED"
    assert "spreadsheet_id" in status["error"]


def test_invalid_credentials_json(settings, monkeypatch):
    monkeypatch.setenv("GOOGLE_CREDENTIALS", "{not json")
    status = SheetsLog(settings).status()
    assert status["code"] == "SHEETS_NOT_CONFIGURED"
    assert "invalid" in status["error"]


def test_failed_connect_not_retried_on_every_call(settings):
    attempts = []

    def opener(s):
        attempts.append(1)
        raise api_error(403)

    log = SheetsLog(settings, opener=opener)
    log.status()
    log.status()
    assert len(attempts) == 1


def test_recent_search_and_filters(settings):
    ws = FakeWorksheet([
        HEADER,
        ["MH12DE1433", ago(50), "upload", "", "", "standard"],
        ["22BH6517A", ago(40), "camera", "", "", "bh"],
        ["MH14AB0001", ago(30), "camera", "", "", "standard"],
    ])
    log = SheetsLog(settings, opener=lambda s: ws)

    rows, total = log.recent()
    assert [r.plate for r in rows] == ["MH14AB0001", "22BH6517A", "MH12DE1433"]  # newest first
    assert total == 3

    assert [r.plate for r in log.recent(query="mh 12")[0]] == ["MH12DE1433"]
    assert [r.plate for r in log.recent(fmt="bh")[0]] == ["22BH6517A"]
    assert [r.plate for r in log.recent(source="camera")[0]] == ["MH14AB0001", "22BH6517A"]

    rows, total = log.recent(limit=1)
    assert len(rows) == 1 and total == 3
