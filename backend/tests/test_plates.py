import pytest

from app.plates import BH, STANDARD, correct_plate, is_valid_plate, plate_format


@pytest.mark.parametrize("plate, fmt", [
    ("MH12DE1433", STANDARD),
    ("DL3CAB1234", STANDARD),
    ("KL07BZ4455", STANDARD),
    ("TN01A1", STANDARD),
    ("KA051234", STANDARD),      # no series letters
    ("22BH6517A", BH),
    ("21BH0234AA", BH),
    ("mh 12 de 1433", STANDARD),  # spaces / lowercase are fine
])
def test_valid_plates(plate, fmt):
    assert plate_format(plate) == fmt
    assert is_valid_plate(plate)


@pytest.mark.parametrize("junk", [
    "",
    "IND",
    "ABCDEF",
    "123456",
    "XX12AB1234",      # not a state code
    "MH12DE14335",     # 5 digit number
    "MH12ABCD1234",    # 4 series letters
    "MH00AB1234",      # RTO 00
    "MH12AB0000",      # number 0000
    "MH12IO1234",      # I and O are never used in series
    "22BH651A",        # BH needs 4 digits
    "22BH6517",        # BH needs letters at the end
    "22XY6517A",
])
def test_junk_rejected(junk):
    assert not is_valid_plate(junk)
    assert correct_plate(junk) is None


@pytest.mark.parametrize("plate", ["MH12DE1433", "DL3CAB1234", "KL07BZ4455", "22BH6517A"])
def test_correct_plates_are_left_alone(plate):
    # the old smart_correct turned DL3CAB1234 into D13CAB1234 and KL07BZ4455 into K107B24455
    match = correct_plate(plate)
    assert match.text == plate
    assert match.fixes == 0


@pytest.mark.parametrize("raw, expected", [
    ("MHI2DE1433", "MH12DE1433"),   # I where a digit belongs
    ("MH12DEI433", "MH12DE1433"),
    ("MH12DE14S3", "MH12DE1453"),   # S -> 5 in the number
    ("KLO7BZ4455", "KL07BZ4455"),   # O -> 0 in the RTO code
    ("KL07B24455", "KL07BZ4455"),   # 2 -> Z in the series
    ("DL3CA81234", "DL3CAB1234"),   # 8 -> B in the series
    ("0D02AB1234", "OD02AB1234"),   # 0 -> O in the state code
    ("22BH65I7A", "22BH6517A"),
    ("2Z8H6517A", "22BH6517A"),     # Z -> 2 in the year, 8 -> B in "BH"
    ("22BH6517S", "22BH6517S"),
    ("MH-12-DE-1433", "MH12DE1433"),
])
def test_ocr_mistakes_fixed_by_position(raw, expected):
    assert correct_plate(raw).text == expected


def test_bh_format_detected():
    match = correct_plate("22BH6517A")
    assert match.format == BH


def test_two_row_plate_joined():
    # bike / auto plates: state + RTO on top, series + number below
    from app.pipeline import best_read, group_rows

    ocr = [
        ([[10, 60], [120, 60], [120, 100], [10, 100]], "DE1433", 0.88),
        ([[30, 10], [100, 10], [100, 50], [30, 50]], "MH12", 0.91),
    ]
    rows = group_rows(ocr)
    assert [t for t, _ in rows] == ["MH12", "DE1433"]

    read = best_read(rows)
    assert read.text == "MH12DE1433"
    assert read.valid


def test_two_row_plate_with_ocr_mistake_and_ind():
    from app.pipeline import best_read, group_rows

    ocr = [
        ([[0, 20], [20, 20], [20, 40], [0, 40]], "IND", 0.99),
        ([[30, 10], [110, 10], [110, 50], [30, 50]], "KLO7", 0.80),
        ([[10, 60], [70, 60], [70, 100], [10, 100]], "B2", 0.75),
        ([[75, 60], [130, 60], [130, 100], [75, 100]], "4455", 0.90),
    ]
    read = best_read(group_rows(ocr))
    assert read.text == "KL07BZ4455"


def test_stray_text_does_not_spoil_plate():
    from app.pipeline import best_read, group_rows

    ocr = [
        ([[10, 10], [200, 10], [200, 40], [10, 40]], "MH12DE1433", 0.9),
        ([[10, 60], [150, 60], [150, 80], [10, 80]], "MARUTI", 0.6),  # dealer sticker below
    ]
    assert best_read(group_rows(ocr)).text == "MH12DE1433"


def test_unreadable_returns_best_raw_text():
    from app.pipeline import best_read, group_rows

    read = best_read(group_rows([([[0, 0], [50, 0], [50, 20], [0, 20]], "XQ7", 0.4)]))
    assert read.text == "XQ7"
    assert not read.valid
