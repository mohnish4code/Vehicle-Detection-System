"""Checks on uploaded images before they reach the model.

The file type is decided by the first bytes of the file, not the name or
the Content-Type header, since both are easy to get wrong (or fake).
"""

import cv2
import numpy as np

from ..config import Settings

ALLOWED = {"jpeg", "png", "webp", "bmp"}


class RejectedUpload(Exception):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def sniff(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data.startswith(b"BM"):
        return "bmp"
    if data[4:8] == b"ftyp" and data[8:12] in (b"heic", b"heix", b"mif1", b"msf1", b"hevc"):
        return "heic"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if data.startswith(b"%PDF"):
        return "pdf"
    return None


def read_limited(upload, max_bytes: int) -> bytes:
    data = upload.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise RejectedUpload("too_large", f"Image is larger than {max_bytes // (1024 * 1024)} MB. "
                                          "Use a smaller photo.")
    return data


def decode_image(data: bytes, settings: Settings) -> np.ndarray:
    if not data:
        raise RejectedUpload("bad_image", "The file is empty.")

    kind = sniff(data)
    if kind == "heic":
        raise RejectedUpload("unsupported_type", "HEIC photos aren't supported. Upload a JPEG or PNG, or set "
                                                 "the iPhone camera format to 'Most Compatible'.")
    if kind not in ALLOWED:
        raise RejectedUpload("unsupported_type", "Unsupported file type. Upload a JPEG, PNG, WebP or BMP image.")

    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise RejectedUpload("bad_image", "This image is damaged or incomplete and couldn't be opened.")

    h, w = image.shape[:2]
    if h * w > settings.api.max_image_megapixels * 1_000_000:
        raise RejectedUpload("too_large", f"Image is {w}x{h}, which is too large. "
                                          f"Use a photo under {settings.api.max_image_megapixels:g} megapixels.")
    if min(h, w) < 32:
        raise RejectedUpload("bad_image", f"Image is only {w}x{h} pixels, too small to find a plate.")
    return image
