"""Open-Meteo forecast API client."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.config import (
    API_TIMEOUT_SECONDS,
    FORECAST_API_BASE,
    CityConfig,
)

logger = logging.getLogger(__name__)

DAILY_VARS = (
    "temperature_2m_max,temperature_2m_min,wind_gusts_10m_max,"
    "precipitation_sum,weather_code"
)
HOURLY_VARS = "temperature_2m,precipitation"


def build_forecast_url(city: CityConfig) -> str:
    """Build the Open-Meteo forecast URL for a city."""
    params = {
        "latitude": city.latitude,
        "longitude": city.longitude,
        "daily": DAILY_VARS,
        "hourly": HOURLY_VARS,
        "timezone": "Pacific/Auckland",
        "forecast_days": 3,
        "forecast_hours": 24,
    }
    return f"{FORECAST_API_BASE}?{urlencode(params)}"


def _normalize_forecast(raw: dict[str, Any]) -> dict[str, Any]:
    daily = raw.get("daily") or {}
    hourly = raw.get("hourly") or {}
    return {
        "daily": {
            "dates": list(daily.get("time") or []),
            "temperature_2m_max": list(daily.get("temperature_2m_max") or []),
            "temperature_2m_min": list(daily.get("temperature_2m_min") or []),
            "wind_gusts_10m_max": list(daily.get("wind_gusts_10m_max") or []),
            "precipitation_sum": list(daily.get("precipitation_sum") or []),
            "weather_code": list(daily.get("weather_code") or []),
        },
        "hourly": {
            "time": list(hourly.get("time") or []),
            "temperature_2m": list(hourly.get("temperature_2m") or []),
            "precipitation": list(hourly.get("precipitation") or []),
        },
    }


def fetch_forecast(city: CityConfig) -> dict[str, Any] | None:
    """Fetch forecast for one city. Returns None on timeout or HTTP error."""
    url = build_forecast_url(city)
    try:
        request = Request(url, headers={"User-Agent": "weather-pulse-nz/1.0"})
        with urlopen(request, timeout=API_TIMEOUT_SECONDS) as response:
            if response.status >= 400:
                logger.error(
                    "Forecast HTTP %s for %s", response.status, city.name
                )
                return None
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("error"):
            logger.error(
                "Forecast API error for %s: %s",
                city.name,
                payload.get("reason"),
            )
            return None
        return _normalize_forecast(payload)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        logger.error("Forecast fetch failed for %s: %s", city.name, exc)
        return None


def fetch_all_forecasts(
    cities: list[CityConfig],
) -> dict[str, dict[str, Any]]:
    """Fetch forecasts in parallel, skipping failed cities."""
    if not cities:
        return {}
    results: dict[str, dict[str, Any]] = {}
    workers = min(8, len(cities))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_forecast, city): city for city in cities}
        for future in as_completed(futures):
            city = futures[future]
            data = future.result()
            if data is not None:
                results[city.name] = data
    return results
