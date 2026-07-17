"""Open-Meteo air quality API client."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.config import API_TIMEOUT_SECONDS, AQI_API_BASE, CityConfig

logger = logging.getLogger(__name__)

UNAVAILABLE = None


def build_aqi_url(city: CityConfig) -> str:
    """Build the Open-Meteo air quality URL for a city."""
    params = {
        "latitude": city.latitude,
        "longitude": city.longitude,
        "current": "us_aqi,pm2_5",
        "timezone": "Pacific/Auckland",
    }
    return f"{AQI_API_BASE}?{urlencode(params)}"


def _normalize_air_quality(raw: dict[str, Any], city_name: str) -> dict[str, Any]:
    current = raw.get("current") or {}
    us_aqi = current.get("us_aqi")
    pm2_5 = current.get("pm2_5")

    if us_aqi is None:
        logger.warning("US_AQI unavailable for %s", city_name)
    if pm2_5 is None:
        logger.warning("PM2.5 unavailable for %s", city_name)

    return {
        "us_aqi": us_aqi if us_aqi is not None else UNAVAILABLE,
        "pm2_5": pm2_5 if pm2_5 is not None else UNAVAILABLE,
    }


def fetch_air_quality(city: CityConfig) -> dict[str, Any] | None:
    """Fetch air quality for one city. Returns None on timeout or HTTP error."""
    url = build_aqi_url(city)
    try:
        request = Request(url, headers={"User-Agent": "weather-pulse-nz/1.0"})
        with urlopen(request, timeout=API_TIMEOUT_SECONDS) as response:
            if response.status >= 400:
                logger.error("AQI HTTP %s for %s", response.status, city.name)
                return None
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("error"):
            logger.error(
                "AQI API error for %s: %s", city.name, payload.get("reason")
            )
            return None
        return _normalize_air_quality(payload, city.name)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        logger.error("AQI fetch failed for %s: %s", city.name, exc)
        return None


def fetch_all_air_quality(
    cities: list[CityConfig],
) -> dict[str, dict[str, Any]]:
    """Fetch air quality in parallel, skipping failed cities."""
    if not cities:
        return {}
    results: dict[str, dict[str, Any]] = {}
    workers = min(8, len(cities))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_air_quality, city): city for city in cities}
        for future in as_completed(futures):
            city = futures[future]
            data = future.result()
            if data is not None:
                results[city.name] = data
    return results
