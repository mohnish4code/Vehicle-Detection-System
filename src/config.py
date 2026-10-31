import json
import logging
import os
import tomllib
from dataclasses import dataclass, field, fields
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = Path(os.environ.get("VDS_CONFIG", ROOT / "config.toml"))

log = logging.getLogger(__name__)


@dataclass
class ModelSettings:
    weights: str = "models/best.pt"
    confidence: float = 0.25


@dataclass
class OcrSettings:
    languages: list[str] = field(default_factory=lambda: ["en"])
    gpu: bool = False
    crop_padding: int = 25
    crop_padding_ratio: float = 0.15
    upscale: int = 2
    min_confidence: float = 0.5
    max_fixes: int = 2
    early_stop_confidence: float = 0.9
    ignore_words: list[str] = field(default_factory=lambda: ["IND", "INDIA"])


@dataclass
class SheetsSettings:
    spreadsheet_id: str = ""
    worksheet: str = ""
    credentials_file: str = "src/credentials.json"
    dedupe_minutes: int = 10
    retries: int = 3
    retry_base_seconds: float = 1.0
    cache_seconds: int = 15


@dataclass
class Settings:
    model: ModelSettings = field(default_factory=ModelSettings)
    ocr: OcrSettings = field(default_factory=OcrSettings)
    sheets: SheetsSettings = field(default_factory=SheetsSettings)

    def path(self, value: str) -> Path:
        """Resolve a path from the config relative to the repo root."""
        p = Path(value)
        return p if p.is_absolute() else ROOT / p


def _cast(raw: str, current):
    if isinstance(current, bool):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(current, (int, float)):
        return type(current)(raw)
    if isinstance(current, list):
        return json.loads(raw) if raw.startswith("[") else [s.strip() for s in raw.split(",")]
    return raw


def load_settings(path: Path = CONFIG_FILE) -> Settings:
    data = {}
    if path.exists():
        with open(path, "rb") as f:
            data = tomllib.load(f)
    else:
        log.warning("Config file %s not found, using defaults", path)

    settings = Settings()
    for section in fields(settings):
        group = getattr(settings, section.name)
        values = data.get(section.name, {})

        for opt in fields(group):
            if opt.name in values:
                setattr(group, opt.name, values[opt.name])

            env_name = f"VDS_{section.name}_{opt.name}".upper()
            if env_name in os.environ:
                setattr(group, opt.name, _cast(os.environ[env_name], getattr(group, opt.name)))

    return settings


@lru_cache
def get_settings() -> Settings:
    return load_settings()


def setup_logging(level: str | None = None):
    logging.basicConfig(
        level=(level or os.environ.get("LOG_LEVEL", "INFO")).upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
