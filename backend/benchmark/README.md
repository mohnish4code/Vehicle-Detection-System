# Benchmark

Labelled plates for [`scripts/evaluate.py`](../scripts/evaluate.py). Image paths are relative to
`data/archive/` (the training dataset, git-ignored). Every box is the dataset's own YOLO label box,
so `--mode ocr` measures OCR alone and `--mode e2e` measures detection + OCR.

| File | Split | Plates | Used for |
|---|---|---|---|
| `dataset_plates.csv` | `dev` | 76 | Tuning the decoder, crop size and review thresholds. Scores on it are *tuning* scores. |
| `heldout_plates.csv` | `test` | 68 (57 distinct) | Reporting only. Never looked at while changing the code. |
| `test_images.csv` | - | 3 | Smoke test on `test_images/` |

## How the sets were made

**Dev** (76): plates read by eye from the training dataset, skipping any that couldn't be read with
certainty. 63 come from `images/train`, 13 from video frames in `images/val`.

**Test** (68), labelled later the same way, from two sources:

- `source=val` (26 rows, 15 distinct plates): frames from the YOLO validation videos. Neither the
  detector's weights nor the OCR tuning saw them. Up to 3 frames per plate, picked to differ in size
  and blur, since consecutive video frames show the same car.
- `source=train` (42 rows, 42 plates): a random sample (`random.Random(42)` over the non-video train
  images that aren't in dev) of the first 64 label boxes, keeping only the plates readable with
  certainty. The YOLO detector *was trained* on these images, so detection is easier than on new
  photos; the OCR and decoder were not tuned on them. Use them for `--mode ocr` numbers.

Any plate that also appears in dev was removed from test (14 plates), plus `MH12DE1433`, which is the
sample photo in `test_images/` used during development. One plate was dropped because the dev
labeller and I read a character differently (`MH01CV6333` / `MH01CY6333`).

Because plates that couldn't be read by eye were skipped, both sets lean towards legible plates;
real-world accuracy on poor photos will be lower.

## Categories

Set by a fixed rule, checked by eye:

| Category | Rule | Dev | Test |
|---|---|---|---|
| `bh` | Bharat-series format | 0 | 0 |
| `two_row` | text on two lines (checked by eye) | 3 | 6 |
| `small` | plate box under 32 px tall | 33 | 32 |
| `standard` | everything else | 40 | 30 |

There are no BH plates and no real night photos in the dataset, so those aren't measured. BH is only
covered by `test_images/testing 1.png` and the unit tests.

## Running

From `backend/`:

```bash
python -m scripts.evaluate --report benchmark/reports/dev.json                     # dev, OCR only
python -m scripts.evaluate --labels benchmark/heldout_plates.csv --report benchmark/reports/test.json
python -m scripts.evaluate --labels benchmark/heldout_plates.csv --mode e2e        # with detection
```

Each `--report` JSON holds the settings, the machine (CPU, commit), the summary, numbers per category
and every plate's result. `wrong_not_flagged` counts plates the app would accept without asking for
review even though the text is wrong.
