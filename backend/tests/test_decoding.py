import numpy as np
import pytest

from app.decoding import decode_plate, greedy, layout_prior, step, START, accepting

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def frames(*spec):
    """Build a CTC probability matrix.

    Each item is either a character (that char with p=0.9), a dict {char: p}
    for an uncertain frame, or "-" for a blank frame. A blank frame is added
    after every character so repeated characters stay separate.
    """
    rows = []

    def row(dist):
        r = np.full(len(ALPHABET) + 1, 1e-4)
        for ch, p in dist.items():
            r[0 if ch == "-" else ALPHABET.index(ch) + 1] = p
        rows.append(r / r.sum())

    for item in spec:
        if item == "-":
            row({"-": 0.95})
            continue
        row(item if isinstance(item, dict) else {item: 0.9, "-": 0.05})
        row({"-": 0.95})
    return np.array(rows)


def best(probs):
    out = decode_plate(probs, ALPHABET)
    return out[0].text if out else None


def test_clean_read():
    p = frames(*"MH12DE1433")
    assert greedy(p, ALPHABET) == "MH12DE1433"
    assert best(p) == "MH12DE1433"
    assert decode_plate(p, ALPHABET)[0].confidence > 0.8


def test_digit_position_uses_best_digit_not_fixed_swap():
    # the model's top guess is "I" but a digit must go here; 1 is the next best guess
    p = frames("M", "H", {"I": 0.55, "1": 0.3, "7": 0.1}, "2", "D", "E", "1", "4", "3", "3")
    assert greedy(p, ALPHABET) == "MHI2DE1433"
    assert best(p) == "MH12DE1433"


def test_letter_lookalike_digit_resolved_by_probability():
    # G vs 6 at the RTO position: the old fixed swap table had no rule for G
    p = frames("R", "J", "1", {"G": 0.5, "6": 0.35, "C": 0.1}, "C", "V", "0", "0", "0", "2")
    assert best(p) == "RJ16CV0002"


def test_state_code_must_exist():
    # "XL" isn't a state, "KL" is
    p = frames({"X": 0.6, "K": 0.35}, "L", "0", "7", "B", "Z", "4", "4", "5", "5")
    assert best(p) == "KL07BZ4455"


def test_letters_in_series_kept():
    # the old code turned DL3CAB1234 into D13CAB1234
    p = frames(*"DL3CAB1234")
    assert best(p) == "DL3CAB1234"


def test_bh_plate():
    p = frames("2", {"Z": 0.6, "2": 0.35}, "B", "H", "6", "5", "1", "7", "A")
    assert best(p) == "22BH6517A"


def test_repeated_characters_need_a_blank():
    p = frames(*"MH12AB1133")
    assert best(p) == "MH12AB1133"


def test_nothing_valid():
    assert decode_plate(frames(*"HELLO"), ALPHABET) == []


def test_prefers_two_digit_rto_outside_delhi():
    # "MH1" + "2" could be RTO 1 + number... the 2-digit RTO layout should win
    assert layout_prior("MH12AB1234") == 0
    assert layout_prior("MH1AB1234") < 0
    assert layout_prior("DL3CAB1234") < 0  # 3-letter series, still allowed
    assert layout_prior("DL3CA1234") == 0


@pytest.mark.parametrize("text, ok", [
    ("MH12DE1433", True), ("22BH6517A", True), ("KA051234", True), ("MH", False), ("XX12", False),
])
def test_grammar(text, ok):
    states = START
    for ch in text:
        states = step(states, ch)
    assert accepting(states) == ok
