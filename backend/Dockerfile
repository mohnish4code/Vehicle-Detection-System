# Backend: FastAPI + YOLOv8 + PaddleOCR via RapidOCR (CPU)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# libgl1 / libglib2.0 for opencv, curl for the healthcheck
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU-only torch first, the default wheel bundles CUDA and is several GB bigger
RUN pip install torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install -r requirements.txt

RUN useradd --create-home app
USER app

# The default OCR engine (PP-OCRv4 via RapidOCR) ships its models in the wheel. EasyOCR,
# if switched on in config.toml, downloads its weights on first start.

COPY --chown=app config.toml .
COPY --chown=app models/best.pt models/best.pt
COPY --chown=app app/ app/

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s \
    CMD curl -fs http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
