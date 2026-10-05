"""Runtime settings, read once from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.environ.get(f"LOTUSLAB_{name}", default)


@dataclass(frozen=True)
class Settings:
    forecast_url: str = field(default_factory=lambda: _env("FORECAST_URL", "https://api.open-meteo.com/v1/forecast"))
    archive_url: str = field(
        default_factory=lambda: _env("ARCHIVE_URL", "https://archive-api.open-meteo.com/v1/archive")
    )
    http_timeout_s: float = field(default_factory=lambda: float(_env("HTTP_TIMEOUT_S", "8")))
    http_backoff_s: float = field(default_factory=lambda: float(_env("HTTP_BACKOFF_S", "0.25")))
    http_retries: int = field(default_factory=lambda: int(_env("HTTP_RETRIES", "2")))
    forecast_ttl_s: float = field(default_factory=lambda: float(_env("FORECAST_TTL_S", "1800")))
    archive_ttl_s: float = field(default_factory=lambda: float(_env("ARCHIVE_TTL_S", "86400")))
    stale_grace_s: float = field(default_factory=lambda: float(_env("STALE_GRACE_S", "86400")))
    weather_cache_size: int = field(default_factory=lambda: int(_env("WEATHER_CACHE_SIZE", "128")))
    result_cache_size: int = field(default_factory=lambda: int(_env("RESULT_CACHE_SIZE", "64")))
    max_days: int = field(default_factory=lambda: int(_env("MAX_DAYS", "366")))
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip() for o in _env("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o
        )
    )
