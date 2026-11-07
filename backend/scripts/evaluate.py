"""Measure plate reading accuracy on a labelled set of images.

Run from backend/:

    python -m scripts.evaluate                          # OCR on the labelled plate boxes
    python -m scripts.evaluate --mode e2e               # detection + OCR on the full images
    python -m scripts.evaluate --labels benchmark/test_images.csv --root test_images --mode e2e

The labels CSV has columns image, plate and optionally x1, y1, x2, y2 (the plate box,
needed for --mode ocr). Image paths are relative to --root.

Reported numbers:
  exact      the plate text is exactly right
  accepted   the app would mark the read as fine (valid format, no review needed)
  wrong+ok   accepted but wrong - the worst case, since nobody is asked to check it
  CER        character error rate (edit distance / plate length)
"""

import argparse
import csv
import json
import logging
import time
from dataclasses import asdict
from pathlib import Path

import cv2

from app.config import ROOT, setup_logging
from app.pipeline import PlatePipeline


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def main():
    parser = argparse.ArgumentParser(description="Evaluate plate reading accuracy")
    parser.add_argument("--labels", default=str(ROOT / "benchmark" / "dataset_plates.csv"))
    parser.add_argument("--root", default=str(ROOT.parent / "data" / "archive"), help="folder the image paths are relative to")
    parser.add_argument("--mode", choices=["ocr", "e2e"], default="ocr")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", help="write per-plate results to this CSV")
    parser.add_argument("--dump", help="write every preprocessing variant's read to this JSON-lines file")
    args = parser.parse_args()

    setup_logging("WARNING")
    root = Path(args.root)
    rows = list(csv.DictReader(open(args.labels, newline="")))
    if args.mode == "ocr":
        rows = [r for r in rows if r.get("x1")]
    if args.limit:
        rows = rows[:args.limit]

    pipe = PlatePipeline().load()
    results = []
    start = time.perf_counter()
    dump = open(args.dump, "w") if args.dump else None

    for i, row in enumerate(rows, 1):
        img = cv2.imread(str(root / row["image"]))
        truth = row["plate"]
        if img is None:
            print(f"!! can't read {row['image']}")
            continue

        t0 = time.perf_counter()
        if args.mode == "ocr":
            box = tuple(int(row[k]) for k in ("x1", "y1", "x2", "y2"))
            read = pipe.read_text(pipe.crop_plate(img, box))
            text, ok = read.text, not pipe.needs_review(read)
        else:
            plates = pipe.detect(img)
            # the plate closest to the truth, if the model found several
            best = min(plates, key=lambda p: edit_distance(p.text, truth), default=None)
            text, ok = (best.text, not best.needs_review) if best else ("", False)
        secs = time.perf_counter() - t0
        if dump and args.mode == "ocr":
            dump.write(json.dumps({"truth": truth, "reads": [asdict(r) for r in pipe.last_reads]}) + "\n")

        dist = edit_distance(text, truth)
        results.append({"image": row["image"], "truth": truth, "read": text, "correct": text == truth,
                        "accepted": ok, "distance": dist, "seconds": round(secs, 2)})
        mark = "ok " if text == truth else "BAD"
        print(f"[{i:3}/{len(rows)}] {mark} {truth:<12} read {text or '-':<12} {'accepted' if ok else 'review':<9} {secs:5.1f}s")

    n = len(results)
    if not n:
        return
    exact = sum(r["correct"] for r in results)
    accepted = [r for r in results if r["accepted"]]
    wrong_ok = sum(not r["correct"] for r in accepted)
    cer = sum(r["distance"] for r in results) / sum(len(r["truth"]) for r in results)

    print()
    print(f"mode      {args.mode}, {n} plates, {time.perf_counter() - start:.0f}s total")
    print(f"exact     {exact}/{n} = {exact / n:.1%}")
    print(f"accepted  {len(accepted)}/{n} = {len(accepted) / n:.1%}"
          f"  (of which correct: {len(accepted) - wrong_ok})")
    print(f"wrong+ok  {wrong_ok}")
    print(f"CER       {cer:.1%}")

    if args.out:
        with open(args.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(results[0]))
            w.writeheader()
            w.writerows(results)


if __name__ == "__main__":
    logging.getLogger("ultralytics").setLevel(logging.WARNING)
    main()
