"""Google Sheets log of confirmed plates.

Connects on first use, so the app still starts (and detection still works)
when credentials are missing or wrong. API calls are retried with backoff
on quota and network errors, and every failure is turned into an AppError
with a message that makes sense to the user.
"""

import json
import logging
import os
import random
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import gspread
import requests
from google.auth.exceptions import GoogleAuthError, TransportError
from google.oauth2.service_account import Credentials

from .config import Settings, get_settings
from .errors import AppError

log = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
# Only needed to find a spreadsheet by its name; it can list file names but not read or change files
DRIVE_LOOKUP_SCOPE = "https://www.googleapis.com/auth/drive.metadata.readonly"
HEADER = ["Plate", "Timestamp (IST)", "Source", "Detection Conf", "OCR Conf", "Format"]

RETRY_STATUS = {429, 500, 502, 503, 504}
# How long to wait before trying to connect again after a failed attempt
RECONNECT_AFTER = 30


class SheetsError(AppError):
    status = 503
    code = "SHEETS_UNAVAILABLE"


class DuplicatePlate(AppError):
    status = 409
    code = "DUPLICATE_PLATE"


@dataclass
class LogEntry:
    plate: str
    timestamp: str
    source: str
    det_conf: float | None = None
    ocr_conf: float | None = None
    format: str | None = None

    def to_row(self) -> list:
        return [self.plate, self.timestamp, self.source,
                "" if self.det_conf is None else round(self.det_conf, 4),
                "" if self.ocr_conf is None else round(self.ocr_conf, 4),
                self.format or ""]

    @classmethod
    def from_row(cls, row: list[str]) -> "LogEntry | None":
        # Rows written by the old Streamlit app only have plate, time, source
        row = list(row) + [""] * (len(HEADER) - len(row))
        plate = row[0].strip().upper()
        if not plate:
            return None
        return cls(plate, row[1].strip(), row[2].strip(),
                   _to_float(row[3]), _to_float(row[4]), row[5].strip() or None)

    def time(self) -> datetime | None:
        try:
            return datetime.strptime(self.timestamp, TIME_FORMAT).replace(tzinfo=IST)
        except ValueError:
            return None

    def as_dict(self) -> dict:
        return asdict(self)


def _to_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_header(row: list[str]) -> bool:
    # Ours, or the old Streamlit app's "PLATE NUMBER | Timestamp | Image Name"
    return len(row) > 1 and row[1].strip().lower().startswith("timestamp")


def scopes_for(settings: Settings) -> list[str]:
    # With the sheet ID we don't need Drive at all
    return [SHEETS_SCOPE] if settings.sheets.spreadsheet_id else [SHEETS_SCOPE, DRIVE_LOOKUP_SCOPE]


def load_credentials(settings: Settings) -> Credentials:
    """Service account key from GOOGLE_CREDENTIALS (the JSON itself),
    GOOGLE_APPLICATION_CREDENTIALS (a path) or the file in config.toml."""
    scopes = scopes_for(settings)
    try:
        if os.environ.get("GOOGLE_CREDENTIALS"):
            info = json.loads(os.environ["GOOGLE_CREDENTIALS"])
            return Credentials.from_service_account_info(info, scopes=scopes)

        path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or settings.sheets.credentials_file
        path = settings.path(path)
        if not path.exists():
            raise SheetsError(
                "Google Sheets isn't set up: no service account key found. "
                "See the README for how to add one.",
                code="SHEETS_NOT_CONFIGURED",
            )
        return Credentials.from_service_account_file(str(path), scopes=scopes)
    except (ValueError, KeyError) as e:  # bad JSON or missing fields in the key
        raise SheetsError("The Google service account key is invalid.", code="SHEETS_NOT_CONFIGURED") from e


def open_worksheet(settings: Settings):
    cfg = settings.sheets
    if not cfg.spreadsheet_id and not cfg.spreadsheet_name:
        raise SheetsError(
            "Google Sheets isn't set up: set spreadsheet_name or spreadsheet_id in config.toml.",
            code="SHEETS_NOT_CONFIGURED",
        )
    client = gspread.authorize(load_credentials(settings))
    if cfg.spreadsheet_id:
        spreadsheet = client.open_by_key(cfg.spreadsheet_id)
    else:
        spreadsheet = client.open(cfg.spreadsheet_name)
    return spreadsheet.worksheet(cfg.worksheet) if cfg.worksheet else spreadsheet.sheet1


def translate_error(e: Exception) -> AppError:
    """Turn a gspread / auth / network exception into something we can show."""
    if isinstance(e, AppError):
        return e
    if isinstance(e, (gspread.SpreadsheetNotFound, gspread.WorksheetNotFound)):
        return SheetsError("The Google Sheet or worksheet wasn't found. Check the sheet name / ID in the config "
                           "and that the sheet is shared with the service account.", code="SHEETS_NOT_FOUND")
    if isinstance(e, gspread.exceptions.APIError):
        if e.code == 429:
            return SheetsError("Google Sheets quota exceeded. Wait a minute and try again.",
                               code="SHEETS_QUOTA", status=429)
        if e.code in (401, 403):
            return SheetsError("No permission to use the Google Sheet. Share it with the service account's "
                               "email as an Editor.", code="SHEETS_PERMISSION")
        if e.code == 404:
            return SheetsError("The Google Sheet wasn't found. Check the sheet name / ID in the config.",
                               code="SHEETS_NOT_FOUND")
        return SheetsError("Google Sheets returned an error. Try again shortly.")
    if isinstance(e, (requests.ConnectionError, requests.Timeout, TransportError)):
        return SheetsError("Can't reach Google Sheets. Check the internet connection.")
    if isinstance(e, GoogleAuthError):
        return SheetsError("Google rejected the service account credentials.", code="SHEETS_PERMISSION")
    return SheetsError("Something went wrong talking to Google Sheets.")


def _retryable(e: Exception) -> bool:
    if isinstance(e, gspread.exceptions.APIError):
        return e.code in RETRY_STATUS
    return isinstance(e, (requests.ConnectionError, requests.Timeout, TransportError))


class SheetsLog:
    def __init__(self, settings: Settings | None = None, opener=open_worksheet, sleep=time.sleep):
        self.settings = settings or get_settings()
        self._opener = opener
        self._sleep = sleep
        self._ws = None
        self._error: AppError | None = None
        self._failed_at = 0.0
        self._lock = threading.RLock()
        self._rows: list[LogEntry] | None = None
        self._rows_at = 0.0

    # -- connection --

    def connect(self, force: bool = False):
        with self._lock:
            if self._ws is not None:
                return self._ws
            if self._error and not force and time.monotonic() - self._failed_at < RECONNECT_AFTER:
                raise self._error

            try:
                ws = self._call(self._opener, self.settings)
                self._ensure_header(ws)
            except Exception as e:
                self._error = translate_error(e)
                self._failed_at = time.monotonic()
                log.warning("Google Sheets connection failed: %s", self._error.message)
                raise self._error from e

            self._ws, self._error = ws, None
            cfg = self.settings.sheets
            log.info("Connected to Google Sheet %s", cfg.spreadsheet_id or repr(cfg.spreadsheet_name))
            return ws

    def status(self) -> dict:
        try:
            self.connect()
            return {"connected": True, "error": None}
        except AppError as e:
            return {"connected": False, "error": e.message, "code": e.code}

    def _ensure_header(self, ws):
        first = self._call(ws.row_values, 1)
        if not first:
            self._call(ws.append_row, HEADER)
            log.info("Sheet was empty, added header row")

    def _call(self, fn, *args, **kwargs):
        retries = self.settings.sheets.retries
        for attempt in range(retries + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                if attempt == retries or not _retryable(e):
                    raise
                delay = self.settings.sheets.retry_base_seconds * 2 ** attempt + random.uniform(0, 0.5)
                log.warning("Sheets call failed (%s), retrying in %.1fs", e, delay)
                self._sleep(delay)

    def _run(self, fn, *args, **kwargs):
        """Call a worksheet method with retries and readable errors."""
        try:
            return self._call(fn, *args, **kwargs)
        except Exception as e:
            err = translate_error(e)
            if err.code in ("SHEETS_PERMISSION", "SHEETS_NOT_FOUND"):
                self._ws = None  # sheet changed under us, reconnect next time
            log.warning("Sheets call failed: %s", e)
            raise err from e

    # -- reading --

    def entries(self, refresh: bool = False) -> list[LogEntry]:
        """All rows, oldest first. Cached for a few seconds to save quota."""
        with self._lock:
            ws = self.connect()
            age = time.monotonic() - self._rows_at
            if refresh or self._rows is None or age > self.settings.sheets.cache_seconds:
                values = self._run(ws.get_all_values)
                if values and _is_header(values[0]):
                    values = values[1:]
                self._rows = [e for e in map(LogEntry.from_row, values) if e]
                self._rows_at = time.monotonic()
            return list(self._rows)

    def recent(self, limit: int = 100, query: str = "", fmt: str | None = None,
               source: str | None = None) -> tuple[list[LogEntry], int]:
        rows = self.entries()
        query = query.strip().upper().replace(" ", "")
        if query:
            rows = [r for r in rows if query in r.plate]
        if fmt:
            rows = [r for r in rows if r.format == fmt]
        if source:
            rows = [r for r in rows if r.source == source]
        rows.reverse()
        return rows[:limit], len(rows)

    # -- writing --

    def last_seen(self, plate: str) -> datetime | None:
        times = [e.time() for e in self.entries() if e.plate == plate]
        times = [t for t in times if t]
        return max(times) if times else None

    def add(self, plate: str, source: str, det_conf=None, ocr_conf=None, fmt=None) -> LogEntry:
        with self._lock:
            now = datetime.now(IST)
            window = timedelta(minutes=self.settings.sheets.dedupe_minutes)
            seen = self.last_seen(plate)
            if seen and now - seen < window:
                mins = max(1, int((now - seen).total_seconds() // 60))
                raise DuplicatePlate(
                    f"{plate} was already logged {mins} min ago. "
                    f"The same plate can only be logged once every {self.settings.sheets.dedupe_minutes} min.",
                    details={"last_logged": seen.strftime(TIME_FORMAT)},
                )

            entry = LogEntry(plate, now.strftime(TIME_FORMAT), source, det_conf, ocr_conf, fmt)
            self._run(self.connect().append_row, entry.to_row())
            self._rows.append(entry)
            log.info("Logged %s (%s)", plate, source)
            return entry
