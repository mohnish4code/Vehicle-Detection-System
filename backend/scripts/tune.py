"""Tune decoder settings and the review flag on the dev set, without re-running OCR each time.

Run from backend/:

    python -m scripts.tune                              # sweep on dev, write benchmark/reports/tuning.json
    python -m scripts.tune --set min_confidence=0.7     # show one setting in detail

EasyOCR's output for all four preprocessing variants of every labelled plate is
computed once and cached in benchmark/cache/ (git-ignored). Each setting is then
just a re-decode, which takes seconds instead of minutes. Only settings that
don't change the OCR input (decoder, voting, early stop, review thresholds) can
be swept this way; crop size changes need scripts/evaluate.py.
"""

import argparse
import csv
import hashlib
import itertools
import json
import logging
import pickle
from dataclasses import asdict, replace
from pathlib import Path

import cv2

from app.config import ROOT, setup_logging
from app.pipeline import PlatePipeline, read_variants

from .evaluate import edit_distance, machine_info, summarize

# settings that change what the OCR engines see, so they're part of the cache key
OCR_INPUT_KEYS = ("target_height", "upscale", "crop_padding", "crop_padding_ratio", "decoder", "languages")
# every engine is cached; each setting below picks which of them vote (and in which order)
ALL_ENGINES = ["paddle", "easyocr"]
ENGINE_CHOICES = [["easyocr"], ["paddle"], ["paddle", "easyocr"], ["easyocr", "paddle"]]


def load_cache(labels: Path, root: Path, rows: list[dict], pipe: PlatePipeline) -> list[dict]:
    """Per plate: {variant name: OCR boxes} for every engine and variant."""
    ocr = pipe.settings.ocr
    key = json.dumps({k: getattr(ocr, k) for k in OCR_INPUT_KEYS} | {"engines": ALL_ENGINES}, sort_keys=True)
    digest = hashlib.sha1((key + labels.read_text()).encode()).hexdigest()[:10]
    path = ROOT / "benchmark" / "cache" / f"{labels.stem}_{digest}.pkl"
    if path.exists():
        return pickle.loads(path.read_bytes())

    ocr.engines = ALL_ENGINES
    pipe.load_ocr()
    cache = []
    for i, row in enumerate(rows, 1):
        img = cv2.imread(str(root / row["image"]))
        box = tuple(int(row[k]) for k in ("x1", "y1", "x2", "y2"))
        cache.append(dict(pipe.variant_ocr(pipe.crop_plate(img, box))))
        print(f"\rOCR {i}/{len(rows)}", end="", flush=True)
    print()
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(pickle.dumps(cache))
    return cache


def score(rows, cache, ocr) -> tuple[dict, list[dict]]:
    results = []
    for row, variants in zip(rows, cache, strict=True):
        ordered = [(name, boxes) for engine in ocr.engines for name, boxes in variants.items()
                   if name.startswith(engine + ":")]
        read, reads = read_variants(iter(ordered), ocr)
        review = not read.valid or read.confidence < ocr.min_confidence or read.fixes > ocr.max_fixes
        results.append({"truth": row["plate"], "read": read.text, "correct": read.text == row["plate"],
                        "accepted": not review, "distance": edit_distance(read.text, row["plate"]),
                        "seconds": 0.0, "variants_used": len(reads), "confidence": read.confidence,
                        "fixes": read.fixes, "valid": read.valid})
    return summarize(results), results


def review_tradeoff(results: list[dict]) -> list[dict]:
    """wrong-but-accepted vs correct-but-flagged for a grid of review thresholds."""
    out = []
    for min_conf, max_fixes in itertools.product([0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9], [0, 1, 2]):
        accepted = [r for r in results if r["valid"] and r["confidence"] >= min_conf and r["fixes"] <= max_fixes]
        out.append({"min_confidence": min_conf, "max_fixes": max_fixes,
                    "wrong_not_flagged": sum(not r["correct"] for r in accepted),
                    "correct_but_flagged": sum(r["correct"] for r in results) - sum(r["correct"] for r in accepted),
                    "accepted": len(accepted)})
    return out


def main():
    parser = argparse.ArgumentParser(description="Sweep decoder settings on cached OCR output")
    parser.add_argument("--labels", default=str(ROOT / "benchmark" / "dataset_plates.csv"))
    parser.add_argument("--root", default=str(ROOT.parent / "data" / "archive"))
    parser.add_argument("--split", default="dev")
    parser.add_argument("--report", default=str(ROOT / "benchmark" / "reports" / "tuning.json"))
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                        help="evaluate only this [ocr] setting (repeatable) and list the failures")
    args = parser.parse_args()

    setup_logging("WARNING")
    labels = Path(args.labels)
    rows = [r for r in csv.DictReader(open(labels, newline="")) if r.get("x1")]
    if args.split:
        rows = [r for r in rows if r.get("split") == args.split]

    pipe = PlatePipeline()
    cache = load_cache(labels, Path(args.root), rows, pipe)
    base = pipe.settings.ocr

    if args.set:
        ocr = replace(base)
        for item in args.set:
            k, v = item.split("=", 1)
            current = getattr(base, k)
            if isinstance(current, list):
                v = v.split(",")
            elif not isinstance(current, str):
                v = type(current)(float(v))
            setattr(ocr, k, v)
        s, results = score(rows, cache, ocr)
        for r in results:
            if not r["correct"]:
                print(f"BAD {r['truth']:<12} read {r['read']:<12} {'accepted' if r['accepted'] else 'review'}")
        print(json.dumps(s, indent=2))
        return

    grid = []
    for engines, early_stop in itertools.product(ENGINE_CHOICES, (0.9, 1.1)):
        ocr = replace(base, engines=engines, early_stop_confidence=early_stop)
        s, results = score(rows, cache, ocr)
        s["variants_used_mean"] = round(sum(r["variants_used"] for r in results) / len(results), 2)
        grid.append({"engines": engines, "early_stop_confidence": early_stop, **s})
        print(f"{'+'.join(engines):<15} early_stop {early_stop:<4} exact {s['exact']}/{s['plates']} "
              f"CER {s['cer']:.1%} wrong+ok {s['wrong_not_flagged']} variants {s['variants_used_mean']}")

    # most plates right, then fewest wrong-but-accepted, then the least OCR work
    best = max(grid, key=lambda g: (g["exact"], -g["wrong_not_flagged"], -g["variants_used_mean"], -g["cer"]))
    ocr = replace(base, engines=best["engines"], early_stop_confidence=best["early_stop_confidence"])
    _, results = score(rows, cache, ocr)
    tradeoff = review_tradeoff(results)
    print(f"\nbest: {best['engines']}, early_stop {best['early_stop_confidence']}")
    print("review thresholds (min_confidence, max_fixes) -> wrong+ok / correct-but-flagged:")
    for t in tradeoff:
        print(f"  {t['min_confidence']:.1f} {t['max_fixes']}  ->  "
              f"{t['wrong_not_flagged']:2} / {t['correct_but_flagged']:2}")

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps({
        "labels": labels.name, "split": args.split, "plates": len(rows), "base_settings": asdict(base),
        "machine": machine_info(), "grid": grid, "best": best, "review_tradeoff": tradeoff,
    }, indent=2))
    print(f"report {args.report}")


if __name__ == "__main__":
    logging.getLogger("ultralytics").setLevel(logging.WARNING)
    main()
