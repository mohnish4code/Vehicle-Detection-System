from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ..plates import normalize

PlateFormat = Literal["standard", "bh"]
Source = Literal["upload", "camera"]
ImageStatus = Literal[
    "ok",               # at least one plate with valid text
    "no_plate",         # model found nothing
    "unreadable",       # plate found, OCR got no text
    "invalid_format",   # plate found, text isn't a valid plate
    "bad_image",        # empty, corrupt or tiny file
    "unsupported_type",
    "too_large",
    "error",            # unexpected failure on this image, details are in the server log
]


class Box(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int


class Plate(BaseModel):
    box: Box
    text: str
    raw_text: str
    det_conf: float
    ocr_conf: float
    valid: bool = Field(description="Text matches a standard or BH plate format")
    needs_review: bool = Field(description="Not valid, low OCR confidence or heavily corrected")
    format: PlateFormat | None
    crop: str = Field(description="Cropped plate as a JPEG data URL")


class ImageResult(BaseModel):
    filename: str
    status: ImageStatus
    message: str | None = None
    width: int | None = None
    height: int | None = None
    plates: list[Plate] = []
    processing_ms: float


class DetectResponse(BaseModel):
    results: list[ImageResult]
    total_ms: float


class LogCreate(BaseModel):
    plate: str = Field(min_length=1, max_length=20, examples=["MH12DE1433"])
    source: Source = "upload"
    det_conf: float | None = Field(None, ge=0, le=1)
    ocr_conf: float | None = Field(None, ge=0, le=1)

    @field_validator("plate")
    @classmethod
    def clean_plate(cls, v: str) -> str:
        return normalize(v)


class LogEntry(BaseModel):
    plate: str
    timestamp: str
    source: str
    det_conf: float | None = None
    ocr_conf: float | None = None
    format: str | None = None


class LogList(BaseModel):
    items: list[LogEntry]
    total: int


class ComponentStatus(BaseModel):
    ok: bool
    error: str | None = None


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    model: ComponentStatus
    sheets: ComponentStatus
