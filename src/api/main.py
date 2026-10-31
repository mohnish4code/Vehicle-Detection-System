"""FastAPI backend.

    uvicorn src.api.main:app --reload
"""

import base64
import logging
import time
from contextlib import asynccontextmanager

import cv2
import numpy as np
from fastapi import FastAPI, File, Query, Request, UploadFile, status

from ..config import Settings, get_settings, setup_logging
from ..errors import AppError
from ..pipeline import PlatePipeline, PlateResult
from ..plates import plate_format
from ..sheets import SheetsLog
from . import schemas
from .errors import install_error_handlers

log = logging.getLogger(__name__)

MESSAGES = {
    "no_plate": "No number plate found. Make sure the plate is clearly visible in the photo.",
    "unreadable": "Plate found but text unclear - try a closer, sharper photo.",
    "invalid_format": "Plate found but the text doesn't match an Indian plate format. Check it before saving.",
    "bad_image": "This file couldn't be opened as an image.",
}


class ModelUnavailable(AppError):
    status = 503
    code = "MODEL_UNAVAILABLE"


def load_pipeline(settings: Settings) -> PlatePipeline:
    pipeline = PlatePipeline(settings)
    try:
        pipeline.load()
    except FileNotFoundError as e:
        log.error("%s", e)
        pipeline.error = f"Model file not found ({settings.model.weights}). Train it or copy best.pt into models/."
    except Exception:
        log.exception("Failed to load the detection model")
        pipeline.error = "The detection model failed to load. Check the server logs."
    return pipeline


def create_app(settings: Settings | None = None, pipeline: PlatePipeline | None = None,
               sheets: SheetsLog | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.pipeline = pipeline or load_pipeline(settings)
        app.state.sheets = sheets or SheetsLog(settings)
        yield

    app = FastAPI(title="Vehicle Plate Detection API", version="2.0.0", lifespan=lifespan)
    install_error_handlers(app)

    @app.get("/api/health", response_model=schemas.Health)
    def health(request: Request):
        pipe: PlatePipeline = request.app.state.pipeline
        model = schemas.ComponentStatus(ok=pipe.loaded, error=None if pipe.loaded else pipe.error)

        sheet_status = request.app.state.sheets.status()
        sheets_ok = schemas.ComponentStatus(ok=sheet_status["connected"], error=sheet_status["error"])

        overall = "ok" if model.ok and sheets_ok.ok else "degraded"
        return schemas.Health(status=overall, model=model, sheets=sheets_ok)

    @app.post("/api/detect", response_model=schemas.DetectResponse)
    def detect(request: Request, files: list[UploadFile] = File(..., description="One or more images")):
        pipe: PlatePipeline = request.app.state.pipeline
        if not pipe.loaded:
            raise ModelUnavailable(pipe.error or "The detection model isn't loaded.")

        start = time.perf_counter()
        results = [process_image(pipe, f) for f in files]
        return schemas.DetectResponse(results=results, total_ms=_ms_since(start))

    @app.post("/api/logs", response_model=schemas.LogEntry, status_code=status.HTTP_201_CREATED)
    def add_log(body: schemas.LogCreate, request: Request):
        fmt = plate_format(body.plate)
        if fmt is None:
            raise AppError(f"{body.plate or 'That'} isn't a valid Indian number plate. Fix the text and try again.",
                           code="INVALID_PLATE", status=422)
        entry = request.app.state.sheets.add(body.plate, body.source, body.det_conf, body.ocr_conf, fmt)
        return entry.as_dict()

    @app.get("/api/logs", response_model=schemas.LogList)
    def list_logs(request: Request,
                  q: str = Query("", max_length=20, description="Search by plate text"),
                  format: schemas.PlateFormat | None = None,
                  source: schemas.Source | None = None,
                  limit: int = Query(100, ge=1, le=1000)):
        items, total = request.app.state.sheets.recent(limit=limit, query=q, fmt=format, source=source)
        return schemas.LogList(items=[e.as_dict() for e in items], total=total)

    return app


def process_image(pipe: PlatePipeline, upload: UploadFile) -> schemas.ImageResult:
    start = time.perf_counter()
    name = upload.filename or "image"

    data = upload.file.read()
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR) if data else None
    if image is None:
        log.info("%s: could not decode image", name)
        return schemas.ImageResult(filename=name, status="bad_image", message=MESSAGES["bad_image"],
                                   processing_ms=_ms_since(start))

    plates = pipe.detect(image)
    h, w = image.shape[:2]

    if not plates:
        image_status = "no_plate"
    elif not any(p.text for p in plates):
        image_status = "unreadable"
    elif not any(p.valid for p in plates):
        image_status = "invalid_format"
    else:
        image_status = "ok"

    return schemas.ImageResult(
        filename=name,
        status=image_status,
        message=MESSAGES.get(image_status),
        width=w,
        height=h,
        plates=[plate_out(p) for p in plates],
        processing_ms=_ms_since(start),
    )


def plate_out(p: PlateResult) -> schemas.Plate:
    x1, y1, x2, y2 = p.box
    return schemas.Plate(
        box=schemas.Box(x1=x1, y1=y1, x2=x2, y2=y2),
        text=p.text,
        raw_text=p.raw_text,
        det_conf=p.det_conf,
        ocr_conf=p.ocr_conf,
        valid=p.valid,
        needs_review=p.needs_review,
        format=p.format,
        crop=encode_jpeg(p.crop),
    )


def encode_jpeg(img: np.ndarray) -> str:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode() if ok else ""


def _ms_since(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


setup_logging()
app = create_app()
