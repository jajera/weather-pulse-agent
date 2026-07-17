"""Wind and AQI threshold classification."""

from __future__ import annotations

from typing import Any

from src.config import (
    AQI_UNHEALTHY_THRESHOLD,
    AQI_WATCH_THRESHOLD,
    WIND_NOTABLE_THRESHOLD_KMH,
)


def classify_thresholds(city_data: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    """Flag wind watchouts and AQI watch/unhealthy cities."""
    wind_watchouts: list[str] = []
    aqi_watch: list[str] = []
    aqi_unhealthy: list[str] = []

    for name, entry in city_data.items():
        forecast = entry.get("forecast") or {}
        daily = forecast.get("daily") or {}
        gusts = daily.get("wind_gusts_10m_max") or []
        if gusts and gusts[0] is not None:
            try:
                if float(gusts[0]) >= WIND_NOTABLE_THRESHOLD_KMH:
                    wind_watchouts.append(name)
            except (TypeError, ValueError):
                pass

        air_quality = entry.get("air_quality") or {}
        us_aqi = air_quality.get("us_aqi")
        if us_aqi is None:
            continue
        try:
            aqi_value = float(us_aqi)
        except (TypeError, ValueError):
            continue
        if aqi_value >= AQI_UNHEALTHY_THRESHOLD:
            aqi_unhealthy.append(name)
        elif aqi_value >= AQI_WATCH_THRESHOLD:
            aqi_watch.append(name)

    return {
        "wind_watchouts": sorted(wind_watchouts),
        "aqi_watch": sorted(aqi_watch),
        "aqi_unhealthy": sorted(aqi_unhealthy),
    }
