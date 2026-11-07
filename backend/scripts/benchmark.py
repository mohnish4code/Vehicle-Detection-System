"""Measure detection + OCR speed per image and throughput with several pipeline instances.

Run from backend/:

    python -m scripts.benchmark                                   # sample images, current config
    python -m scripts.benchmark --weights models/best.onnx --label onnx
    python -m scripts.benchmark --instances 2 --concurrency 4

Every image is run once to warm up, then --repeat times. Latency is per image,
end to end (YOLO + crop + OCR). Throughput sends --concurrency images at a time
through a pool of --instances pipelines, like the API does. Results are added to
benchmark/reports/benchmark.json under --label.
"""

import argparse
import json
import logging
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

from app.config import ROOT, get_settings, setup_logging
from app.pipeline import PipelinePool, PlatePipeline

from .evaluate import machine_info


def percentile(values: list[float], p: float) -> float:
    return float(np.percentile(values, p))


def main():
    parser = argparse.ArgumentParser(description="Benchmark the plate pipeline")
    parser.add_argument("--images", default=str(ROOT / "test_images"))
    parser.add_argument("--weights", help="detector weights (.pt or .onnx), default from config")
    parser.add_argument("--engines", help="comma separated OCR engines, default from config")
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--instances", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--label", default="default")
    parser.add_argument("--report", default=str(ROOT / "benchmark" / "reports" / "benchmark.json"))
    args = parser.parse_args()

    setup_logging("WARNING")
    logging.getLogger("ultralytics").setLevel(logging.WARNING)
    settings = get_settings()
    if args.weights:
        settings.model.weights = args.weights
    if args.engines:
        settings.ocr.engines = args.engines.split(",")

    images = [(p.name, cv2.imread(str(p))) for p in sorted(Path(args.images).iterdir())
              if p.suffix.lower() in (".jpg", ".jpeg", ".png")]

    start = time.perf_counter()
    pipes = [PlatePipeline(settings).load() for _ in range(args.instances)]
    load_s = time.perf_counter() - start
    pool = PipelinePool(pipes)

    for _, img in images:  # warm-up
        pool.detect(img)

    latencies = []
    for _ in range(args.repeat):
        for _, img in images:
            t0 = time.perf_counter()
            pipes[0].detect(img)
            latencies.append(time.perf_counter() - t0)

    jobs = [img for _ in range(args.repeat) for _, img in images]
    t0 = time.perf_counter()
    with ThreadPoolExecutor(args.concurrency) as ex:
        list(ex.map(pool.detect, jobs))
    wall = time.perf_counter() - t0

    result = {
        "label": args.label,
        "weights": settings.model.weights,
        "engines": settings.ocr.engines,
        "images": [name for name, _ in images],
        "repeat": args.repeat,
        "load_seconds": round(load_s, 1),
        "latency_ms": {"mean": round(statistics.mean(latencies) * 1000, 1),
                       "p50": round(percentile(latencies, 50) * 1000, 1),
                       "p95": round(percentile(latencies, 95) * 1000, 1)},
        "throughput": {"instances": args.instances, "concurrency": args.concurrency,
                       "images": len(jobs), "images_per_second": round(len(jobs) / wall, 2)},
        "machine": machine_info(),
    }
    print(json.dumps(result, indent=2))

    path = Path(args.report)
    report = json.loads(path.read_text()) if path.exists() else {"runs": []}
    report["runs"] = [r for r in report["runs"] if r["label"] != args.label] + [result]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
