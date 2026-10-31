import json
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import gspread

from .config import get_settings

log = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_sheet = None


def get_sheet():
    """Connect on first use instead of at import, so a missing key file doesn't break everything."""
    global _sheet
    if _sheet is None:
        cfg = get_settings()
        if "GOOGLE_CREDENTIALS" in os.environ:
            client = gspread.service_account_from_dict(json.loads(os.environ["GOOGLE_CREDENTIALS"]), scopes=SCOPES)
        else:
            client = gspread.service_account(filename=cfg.path(cfg.sheets.credentials_file), scopes=SCOPES)
        _sheet = client.open(cfg.sheets.spreadsheet_name).sheet1
        log.info("Connected to Google Sheet %r", cfg.sheets.spreadsheet_name)
    return _sheet


def save_to_sheets(plate: str, source: str):
    timestamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    get_sheet().append_row([plate, timestamp, source])
    log.info("Saved %s to sheet", plate)
