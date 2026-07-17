"""Shared pytest fixtures and helpers."""

from __future__ import annotations

from typing import Any


def sample_forecast(
    max_temp: float = 18.0,
    min_temp: float = 8.0,
    gust: float = 30.0,
    precip: float = 1.0,
) -> dict[str, Any]:
    return {
        "daily": {
            "dates": ["2026-07-17", "2026-07-18", "2026-07-19"],
            "temperature_2m_max": [max_temp, max_temp - 1, max_temp],
            "temperature_2m_min": [min_temp, min_temp + 1, min_temp],
            "wind_gusts_10m_max": [gust, gust - 5, gust],
            "precipitation_sum": [precip, 0.0, precip],
            "weather_code": [1, 2, 3],
        },
        "hourly": {
            "time": ["2026-07-17T06:00"],
            "temperature_2m": [min_temp + 1],
            "precipitation": [0.0],
        },
    }


def sample_city(
    name: str,
    island: str = "north",
    max_temp: float = 18.0,
    min_temp: float = 8.0,
    gust: float = 30.0,
    precip: float = 1.0,
    us_aqi: float | None = 40,
    pm2_5: float | None = 10.0,
) -> dict[str, Any]:
    return {
        "coordinates": {"latitude": -36.85, "longitude": 174.76},
        "island": island,
        "forecast": sample_forecast(max_temp, min_temp, gust, precip),
        "air_quality": {"us_aqi": us_aqi, "pm2_5": pm2_5},
    }


def sample_payload(cities: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    from src.compute.extremes import compute_extremes
    from src.compute.thresholds import classify_thresholds

    if cities is None:
        cities = {
            "Auckland": sample_city("Auckland", "north", 20, 10, 42, 2, 40),
            "Wellington": sample_city("Wellington", "north", 15, 9, 55, 0, 50),
            "Christchurch": sample_city("Christchurch", "south", 12, 2, 25, 5, 30),
            "Queenstown": sample_city("Queenstown", "south", 10, -1, 20, 1, 25),
        }
    return {
        "run_timestamp": "2026-07-17T06:30:00+12:00",
        "cities": cities,
        "extremes": compute_extremes(cities),
        "threshold_flags": classify_thresholds(cities),
    }
