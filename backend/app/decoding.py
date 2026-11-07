"""Read plate text from OCR character probabilities, only allowing valid plates.

EasyOCR's recognizer gives, for every column ("frame") of the text image, a
probability for each character plus a "blank" (CTC). Normally the most likely
character per frame is taken, which happily produces things like MHI2DE1433.

Here we search for the most probable text that is also a valid Indian plate,
so an "I" in a digit position becomes whatever digit the model thought was most
likely there - not a fixed I -> 1 swap. It's a CTC prefix beam search that
drops any prefix that can't be completed into a plate.
"""

import math
from dataclasses import dataclass

import numpy as np

from .plates import BH, SERIES_LETTERS, STANDARD, STATE_CODES, plate_format

DIGITS = "0123456789"
FIRST_LETTERS = {s[0] for s in STATE_CODES}

# Soft preferences between layouts that are all technically valid. Values are
# log-probability penalties added to the final score.
PRIOR_ONE_DIGIT_RTO = math.log(0.15)  # only Delhi (DL 3C ...) really uses these
PRIOR_THREE_LETTER_SERIES = math.log(0.5)


@dataclass(frozen=True)
class Decoded:
    text: str
    format: str
    logp: float  # log P(text | image) under the CTC model
    confidence: float  # per-character geometric mean of that probability


# -- plate grammar as a small NFA over characters --
# States: ("st",) start of state code, ("st1", c) after its first letter,
# ("rto", n) n RTO digits, ("ser", n) n series letters, ("num", n) n number digits,
# ("bh", i) position i in the BH layout YY BH NNNN X(X).

START = frozenset({("st",), ("bh", 0)})
BH_LAYOUT = [DIGITS, DIGITS, "B", "H", DIGITS, DIGITS, DIGITS, DIGITS, SERIES_LETTERS, SERIES_LETTERS]


def _step_one(state: tuple, ch: str) -> list[tuple]:
    kind = state[0]
    digit = ch in DIGITS
    if kind == "st":
        return [("st1", ch)] if ch in FIRST_LETTERS else []
    if kind == "st1":
        return [("rto", 0)] if state[1] + ch in STATE_CODES else []
    if kind == "rto":
        n = state[1]
        out = []
        if digit and n < 2:
            out.append(("rto", n + 1))
        if digit and n >= 1:
            out.append(("num", 1))  # no series letters
        if not digit and n >= 1 and ch in SERIES_LETTERS:
            out.append(("ser", 1))
        return out
    if kind == "ser":
        n = state[1]
        if digit:
            return [("num", 1)]
        return [("ser", n + 1)] if n < 3 and ch in SERIES_LETTERS else []
    if kind == "num":
        return [("num", state[1] + 1)] if digit and state[1] < 4 else []
    if kind == "bh":
        i = state[1]
        return [("bh", i + 1)] if i < len(BH_LAYOUT) and ch in BH_LAYOUT[i] else []
    return []


def step(states: frozenset, ch: str) -> frozenset:
    return frozenset(s for state in states for s in _step_one(state, ch))


def accepting(states: frozenset) -> bool:
    return any((s[0] == "num" and s[1] >= 1) or (s[0] == "bh" and s[1] in (9, 10)) for s in states)


def layout_prior(text: str) -> float:
    if plate_format(text) != STANDARD:
        return 0.0
    prior = 0.0
    rto = len(text[2:]) - len(text[2:].lstrip(DIGITS))
    if rto == 1 and not text.startswith("DL"):
        prior += PRIOR_ONE_DIGIT_RTO
    body = text[2 + rto:]
    series = len(body) - len(body.lstrip(SERIES_LETTERS))
    if series == 3:
        prior += PRIOR_THREE_LETTER_SERIES
    return prior


# -- CTC decoding --

NEG_INF = -math.inf


def _logadd(a: float, b: float) -> float:
    if a == NEG_INF:
        return b
    if b == NEG_INF:
        return a
    m = max(a, b)
    return m + math.log1p(math.exp(-abs(a - b)))


def greedy(probs: np.ndarray, alphabet: str) -> str:
    """Plain best-per-frame decoding (what EasyOCR does), for comparison / display."""
    out, prev = [], 0
    for idx in probs.argmax(axis=1):
        if idx != 0 and idx != prev:
            out.append(alphabet[idx - 1])
        prev = idx
    return "".join(out)


def decode_plate(probs: np.ndarray, alphabet: str, beam_width: int = 32, top_k: int = 8,
                 n_best: int = 5) -> list[Decoded]:
    """Most probable valid plates for a (frames x 1+len(alphabet)) probability matrix.

    Column 0 is the CTC blank, column i is alphabet[i-1]. Returns up to n_best
    plates, best first; empty if nothing valid fits.
    """
    logp = np.log(np.clip(probs, 1e-12, 1.0))
    # prefix -> [log p ending in blank, log p ending in a char, grammar states]
    beams: dict[str, list] = {"": [0.0, NEG_INF, START]}

    for t in range(logp.shape[0]):
        frame = logp[t]
        # only consider the likeliest characters in each frame
        cand = np.argpartition(-frame[1:], top_k)[:top_k] + 1 if len(alphabet) > top_k else range(1, len(alphabet) + 1)
        nxt: dict[str, list] = {}

        for prefix, (lb, lnb, states) in beams.items():
            total = _logadd(lb, lnb)
            e = nxt.setdefault(prefix, [NEG_INF, NEG_INF, states])
            e[0] = _logadd(e[0], total + frame[0])  # blank
            if prefix:  # same char continues, no new character
                last_idx = alphabet.index(prefix[-1]) + 1
                e[1] = _logadd(e[1], lnb + frame[last_idx])

            for idx in cand:
                ch = alphabet[idx - 1]
                new_states = step(states, ch)
                if not new_states:
                    continue
                # a repeated character needs a blank in between
                p = (lb if prefix and prefix[-1] == ch else total) + frame[idx]
                e2 = nxt.setdefault(prefix + ch, [NEG_INF, NEG_INF, new_states])
                e2[1] = _logadd(e2[1], p)

        beams = dict(sorted(nxt.items(), key=lambda kv: -_logadd(kv[1][0], kv[1][1]))[:beam_width])

    results = []
    for prefix, (lb, lnb, states) in beams.items():
        fmt = plate_format(prefix) if accepting(states) else None
        if fmt not in (STANDARD, BH):
            continue
        lp = _logadd(lb, lnb)
        results.append(Decoded(prefix, fmt, lp, math.exp(lp / len(prefix))))

    results.sort(key=lambda d: d.logp + layout_prior(d.text), reverse=True)
    return results[:n_best]
