"""Indian number plate parsing, OCR correction and validation.

Two formats are supported:

* Standard: SS RR XXX NNNN
  2 letter state code, 1-2 digit RTO code, 0-3 letter series, 1-4 digit number.
  e.g. MH12DE1433, DL3CAB1234, KL07BZ4455
* Bharat (BH) series: YY BH NNNN XX
  2 digit year, "BH", 4 digit number, 1-2 letters. e.g. 22BH6517A

OCR often confuses 0/O, 1/I, 2/Z, 5/S and 8/B. Correction only swaps a
character when the plate layout expects the other type at that position,
so a letter that belongs in the state code or series is never turned into
a digit (and the other way round).
"""

import re
from dataclasses import dataclass
from itertools import product

STATE_CODES = frozenset({
    "AN", "AP", "AR", "AS", "BR", "CG", "CH", "DD", "DL", "DN", "GA", "GJ",
    "HP", "HR", "JH", "JK", "KA", "KL", "LA", "LD", "MH", "ML", "MN", "MP",
    "MZ", "NL", "OD", "OR", "PB", "PY", "RJ", "SK", "TG", "TN", "TR", "TS",
    "UK", "UA", "UP", "WB",
})

TO_DIGIT = {"O": "0", "I": "1", "Z": "2", "S": "5", "B": "8"}
TO_LETTER = {v: k for k, v in TO_DIGIT.items()}

# I and O are not issued in series letters because they look like 1 and 0
SERIES_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"

_STATES = "|".join(sorted(STATE_CODES))
STANDARD_RE = re.compile(
    rf"(?P<state>{_STATES})(?P<rto>\d{{1,2}})(?P<series>[{SERIES_LETTERS}]{{0,3}})(?P<number>\d{{1,4}})"
)
BH_RE = re.compile(rf"(?P<year>\d{{2}})BH(?P<number>\d{{4}})(?P<series>[{SERIES_LETTERS}]{{1,2}})")

STANDARD = "standard"
BH = "bh"


@dataclass(frozen=True)
class PlateMatch:
    text: str
    format: str
    fixes: int  # how many characters were swapped to get here


def normalize(text: str) -> str:
    """Uppercase and drop everything that isn't A-Z or 0-9."""
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def plate_format(text: str) -> str | None:
    """Return "standard" or "bh" if text is a valid plate, otherwise None."""
    text = normalize(text)

    m = STANDARD_RE.fullmatch(text)
    if m and int(m["rto"]) > 0 and int(m["number"]) > 0:
        return STANDARD

    m = BH_RE.fullmatch(text)
    if m and int(m["number"]) > 0:
        return BH

    return None


def is_valid_plate(text: str) -> bool:
    return plate_format(text) is not None


def _as_digits(chunk: str) -> tuple[str, int] | None:
    out, fixes = [], 0
    for ch in chunk:
        if ch.isdigit():
            out.append(ch)
        elif ch in TO_DIGIT:
            out.append(TO_DIGIT[ch])
            fixes += 1
        else:
            return None
    return "".join(out), fixes


def _as_letters(chunk: str, allowed: str) -> tuple[str, int] | None:
    out, fixes = [], 0
    for ch in chunk:
        if ch.isalpha():
            if ch not in allowed:
                return None
            out.append(ch)
        elif ch in TO_LETTER and TO_LETTER[ch] in allowed:
            out.append(TO_LETTER[ch])
            fixes += 1
        else:
            return None
    return "".join(out), fixes


def _split(text: str, sizes: tuple[int, ...]) -> list[str]:
    parts, pos = [], 0
    for size in sizes:
        parts.append(text[pos:pos + size])
        pos += size
    return parts


def _standard_candidates(text: str):
    for rto_len, series_len in product((2, 1), (0, 1, 2, 3)):
        number_len = len(text) - 2 - rto_len - series_len
        if not 1 <= number_len <= 4:
            continue

        state, rto, series, number = _split(text, (2, rto_len, series_len, number_len))
        parts = [
            _as_letters(state, SERIES_LETTERS + "IO"),
            _as_digits(rto),
            _as_letters(series, SERIES_LETTERS),
            _as_digits(number),
        ]
        if None in parts:
            continue

        fixed = "".join(p[0] for p in parts)
        if plate_format(fixed) != STANDARD:
            continue

        fixes = sum(p[1] for p in parts)
        # On a tie prefer the common layout: 2 digit RTO and 4 digit number
        rank = (fixes, number_len != 4, rto_len != 2)
        yield rank, PlateMatch(fixed, STANDARD, fixes)


def _bh_candidates(text: str):
    for series_len in (1, 2):
        if len(text) != 8 + series_len:
            continue

        year, bh, number, series = _split(text, (2, 2, 4, series_len))
        parts = [
            _as_digits(year),
            _as_letters(bh, "BH"),
            _as_digits(number),
            _as_letters(series, SERIES_LETTERS),
        ]
        if None in parts:
            continue

        fixed = "".join(p[0] for p in parts)
        if plate_format(fixed) != BH:
            continue

        fixes = sum(p[1] for p in parts)
        yield (fixes, False, False), PlateMatch(fixed, BH, fixes)


def correct_plate(raw: str) -> PlateMatch | None:
    """Fix common OCR mix-ups based on position and return the best valid plate.

    Every way of splitting the text into the plate fields is tried and the one
    that needs the fewest character swaps wins. Returns None if no layout fits.
    """
    text = normalize(raw)
    if not text:
        return None

    candidates = [*_standard_candidates(text), *_bh_candidates(text)]
    if not candidates:
        return None

    return min(candidates, key=lambda c: c[0])[1]
