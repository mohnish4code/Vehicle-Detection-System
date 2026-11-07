"""Measure plate reading accuracy on a labelled set of images.

Run from backend/:

    python -m scripts.evaluate                          # OCR on the labelled plate boxes
    python -m scripts.evaluate --mode e2e               # detection + OCR on the full images
    python -m scripts.evaluate --labels benchmark/test_images.csv --root test_images --mode e2e
    python -m scripts.evaluate --split test --report benchmark/reports/test.json

The labels CSV has columns image, plate and optionally x1, y1, x2, y2 (the plate box,
needed for --mode ocr), split (dev / test) and category (e.g. standard, bh, two_row).
Image paths are relative to --root.

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
import os
import platform
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime
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


def cpu_name() -> str:
    try:
        if sys.platform == "win32":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            return winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        if Path("/proc/cpuinfo").exists():
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


def machine_info() -> dict:
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                                cwd=ROOT).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "app", "config.toml"],
                                    capture_output=True, text=True, cwd=ROOT).stdout.strip())
    except OSError:
        commit, dirty = "", False
    return {"cpu": cpu_name(), "logical_cpus": os.cpu_count(), "platform": platform.platform(),
            "python": platform.python_version(), "git_commit": commit + ("+changes" if dirty else ""),
            "date": datetime.now().isoformat(timespec="seconds")}


def summarize(results: list[dict]) -> dict:
    n = len(results)
    accepted = [r for r in results if r["accepted"]]
    wrong_ok = sum(not r["correct"] for r in accepted)
    exact = sum(r["correct"] for r in results)
    flagged_correct = sum(r["correct"] and not r["accepted"] for r in results)
    return {
        "plates": n,
        "exact": exact,
        "exact_rate": round(exact / n, 4),
        "cer": round(sum(r["distance"] for r in results) / sum(len(r["truth"]) for r in results), 4),
        "accepted": len(accepted),
        "accepted_correct": len(accepted) - wrong_ok,
        "wrong_not_flagged": wrong_ok,
        "correct_but_flagged": flagged_correct,
        "seconds_mean": round(sum(r["seconds"] for r in results) / n, 2),
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate plate reading accuracy")
    parser.add_argument("--labels", default=str(ROOT / "benchmark" / "dataset_plates.csv"))
    parser.add_argument("--root", default=str(ROOT.parent / "data" / "archive"),
                        help="folder the image paths are relative to")
    parser.add_argument("--mode", choices=["ocr", "e2e"], default="ocr")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", help="write per-plate results to this CSV")
    parser.add_argument("--dump", help="write every preprocessing variant's read to this JSON-lines file")
    parser.add_argument("--split", help="only plates with this value in the split column (dev / test)")
    parser.add_argument("--report", help="write the summary, per-category numbers and per-plate results as JSON")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                        help="override an [ocr] setting for this run, e.g. --set target_height=100")
    args = parser.parse_args()

    setup_logging("WARNING")
    root = Path(args.root)
    rows = list(csv.DictReader(open(args.labels, newline="")))
    if args.split:
        rows = [r for r in rows if r.get("split") == args.split]
    if args.mode == "ocr":
        rows = [r for r in rows if r.get("x1")]
    if args.limit:
        rows = rows[:args.limit]

    pipe = PlatePipeline()
    for item in args.set:
        key, value = item.split("=", 1)
        current = getattr(pipe.settings.ocr, key)
        if isinstance(current, list):
            value = value.split(",")
        elif not isinstance(current, str):
            value = type(current)(float(value))
        setattr(pipe.settings.ocr, key, value)
    pipe.load()
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
                        "accepted": ok, "distance": dist, "seconds": round(secs, 2),
                        "category": row.get("category") or "", "source": row.get("source") or ""})
        mark = "ok " if text == truth else "BAD"
        status = 'accepted' if ok else 'review'
        print(f"[{i:3}/{len(rows)}] {mark} {truth:<12} read {text or '-':<12} {status:<9} {secs:5.1f}s")

    n = len(results)
    if not n:
        return
    total_secs = time.perf_counter() - start
    s = summarize(results)

    print()
    print(f"mode      {args.mode}, {n} plates, {total_secs:.0f}s total")
    print(f"exact     {s['exact']}/{n} = {s['exact_rate']:.1%}")
    print(f"accepted  {s['accepted']}/{n} = {s['accepted'] / n:.1%}  (of which correct: {s['accepted_correct']})")
    print(f"wrong+ok  {s['wrong_not_flagged']}")
    print(f"CER       {s['cer']:.1%}")

    groups = {}
    for key in ("category", "source"):
        values = sorted({r[key] for r in results if r[key]})
        groups[key] = {v: summarize([r for r in results if r[key] == v]) for v in values}
        for v, gs in groups[key].items():
            print(f"  {v:<10} {gs['exact']}/{gs['plates']} exact, CER {gs['cer']:.1%}, "
                  f"wrong+ok {gs['wrong_not_flagged']}")
    by_category, by_source = groups["category"], groups["source"]

    if args.report:
        report = {
            "labels": Path(args.labels).name, "split": args.split or "all", "mode": args.mode,
            "settings": asdict(pipe.settings.ocr), "detector_confidence": pipe.settings.model.confidence,
            "machine": machine_info(), "total_seconds": round(total_secs, 1),
            "summary": s, "by_category": by_category, "by_source": by_source, "results": results,
        }
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, indent=2))
        print(f"report    {args.report}")

    if args.out:
        with open(args.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(results[0]))
            w.writeheader()
            w.writerows(results)


if __name__ == "__main__":
    logging.getLogger("ultralytics").setLevel(logging.WARNING)
    main()
