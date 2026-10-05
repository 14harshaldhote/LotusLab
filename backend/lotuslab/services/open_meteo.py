"""Open-Meteo adapter: fetch hourly weather and normalise it.

Open-Meteo is free for non-commercial use without an API key; data is licensed
CC BY 4.0 and must be attributed (see ``ATTRIBUTION``).

Endpoint choice:
* forecast API for ranges within the last ~90 days up to 16 days ahead;
* archive (ERA5 reanalysis) API for ranges that end at least 5 days ago.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from dataclasses import dataclass

import httpx

from ..config import Settings
from ..core.weather import HourlyWeather, WeatherError, normalise

log = logging.getLogger("lotuslab.open_meteo")

ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"

# provider variable -> our normalised column
HOURLY_VARIABLES = {
    "temperature_2m": "temperature_c",
    "precipitation": "precipitation_mm",
    "cloud_cover": "cloud_cover_pct",
    "wind_speed_10m": "wind_speed_ms",
    "relative_humidity_2m": "relative_humidity_pct",
    "shortwave_radiation": "shortwave_wm2",
    "et0_fao_evapotranspiration": "et0_mm",
}

FORECAST_PAST_DAYS = 90
FORECAST_FUTURE_DAYS = 15
ARCHIVE_LAG_DAYS = 5


class ProviderError(Exception):
    """The provider rejected the request (bad range, bad coordinates)."""


class ProviderUnavailable(Exception):
    """The provider could not be reached or kept failing after retries."""


@dataclass(frozen=True)
class WeatherResult:
    weather: HourlyWeather
    endpoint: str  # "forecast" | "archive"
    timezone: str


def choose_endpoint(start: dt.date, end: dt.date, today: dt.date) -> str:
    if end < start:
        raise ProviderError("end date is before start date")
    if end > today + dt.timedelta(days=FORECAST_FUTURE_DAYS):
        raise ProviderError(f"forecasts reach at most {FORECAST_FUTURE_DAYS} days ahead")
    if start >= today - dt.timedelta(days=FORECAST_PAST_DAYS):
        return "forecast"
    if end <= today - dt.timedelta(days=ARCHIVE_LAG_DAYS):
        return "archive"
    raise ProviderError(
        f"ranges older than {FORECAST_PAST_DAYS} days must end at least {ARCHIVE_LAG_DAYS} days ago; split the range"
    )


class OpenMeteoClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.http_timeout_s),
            transport=transport,
            headers={"User-Agent": "LotusLab/0.1 (+https://github.com/14harshaldhote/LotusLab)"},
        )
        self.requests_made = 0

    async def aclose(self) -> None:
        await self._client.aclose()

    async def hourly(
        self, lat: float, lon: float, start: dt.date, end: dt.date, today: dt.date | None = None
    ) -> WeatherResult:
        endpoint = choose_endpoint(start, end, today or dt.datetime.now(dt.timezone.utc).date())
        url = self.settings.forecast_url if endpoint == "forecast" else self.settings.archive_url
        params = {
            "latitude": f"{lat:.4f}",
            "longitude": f"{lon:.4f}",
            "hourly": ",".join(HOURLY_VARIABLES),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "timezone": "auto",
            "timeformat": "unixtime",
            "wind_speed_unit": "ms",
        }
        payload = await self._get_json(url, params)
        return WeatherResult(parse(payload), endpoint, str(payload.get("timezone", "GMT")))

    async def _get_json(self, url: str, params: dict[str, str]) -> dict:
        attempts = self.settings.http_retries + 1
        last: Exception | None = None
        for attempt in range(attempts):
            if attempt:
                await asyncio.sleep(min(self.settings.http_backoff_s * 3 ** (attempt - 1), 3.0))
            try:
                self.requests_made += 1
                resp = await self._client.get(url, params=params)
            except httpx.HTTPError as exc:  # timeouts, DNS, connection resets
                last = exc
                log.warning("open-meteo transport error (attempt %d/%d): %s", attempt + 1, attempts, exc)
                continue
            if resp.status_code == 400:
                reason = _reason(resp)
                raise ProviderError(reason)
            if resp.status_code == 429 or resp.status_code >= 500:
                last = ProviderUnavailable(f"HTTP {resp.status_code}")
                log.warning("open-meteo HTTP %d (attempt %d/%d)", resp.status_code, attempt + 1, attempts)
                continue
            if resp.status_code != 200:
                raise ProviderUnavailable(f"unexpected HTTP {resp.status_code}")
            try:
                return resp.json()
            except ValueError as exc:
                raise ProviderUnavailable("provider returned invalid JSON") from exc
        raise ProviderUnavailable(f"weather provider unavailable after {attempts} attempts: {last}")


def parse(payload: dict) -> HourlyWeather:
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict) or "time" not in hourly:
        raise ProviderUnavailable("provider response has no hourly block")
    cols = {ours: hourly.get(theirs) for theirs, ours in HOURLY_VARIABLES.items() if theirs in hourly}
    try:
        return normalise(hourly["time"], cols, int(payload.get("utc_offset_seconds", 0)))
    except WeatherError as exc:
        raise ProviderUnavailable(f"provider data unusable: {exc}") from exc


def _reason(resp: httpx.Response) -> str:
    try:
        return str(resp.json().get("reason", "request rejected by weather provider"))
    except ValueError:
        return "request rejected by weather provider"
