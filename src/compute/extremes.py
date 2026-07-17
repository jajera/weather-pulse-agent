"""NZ extremes and island contrast aggregates."""

from __future__ import annotations

from typing import Any


def _first_day_value(city_entry: dict[str, Any], key: str) -> float | None:
    forecast = city_entry.get("forecast") or {}
    daily = forecast.get("daily") or {}
    values = daily.get(key) or []
    if not values or values[0] is None:
        return None
    try:
        return float(values[0])
    except (TypeError, ValueError):
        return None


def _cities_with_metric(
    city_data: dict[str, dict[str, Any]], key: str
) -> list[tuple[str, float]]:
    found: list[tuple[str, float]] = []
    for name, entry in city_data.items():
        value = _first_day_value(entry, key)
        if value is not None:
            found.append((name, value))
    return found


def _extreme_group(
    pairs: list[tuple[str, float]], *, highest: bool
) -> dict[str, Any] | None:
    if not pairs:
        return None
    target = max(v for _, v in pairs) if highest else min(v for _, v in pairs)
    cities = sorted(name for name, value in pairs if value == target)
    return {"cities": cities, "value": target}


def _island_avg(
    city_data: dict[str, dict[str, Any]], island: str
) -> dict[str, float | None]:
    max_temps: list[float] = []
    min_temps: list[float] = []
    gusts: list[float] = []
    for entry in city_data.values():
        if entry.get("island") != island:
            continue
        max_t = _first_day_value(entry, "temperature_2m_max")
        min_t = _first_day_value(entry, "temperature_2m_min")
        gust = _first_day_value(entry, "wind_gusts_10m_max")
        if max_t is not None:
            max_temps.append(max_t)
        if min_t is not None:
            min_temps.append(min_t)
        if gust is not None:
            gusts.append(gust)
    return {
        "avg_max_temp": (sum(max_temps) / len(max_temps)) if max_temps else None,
        "avg_min_temp": (sum(min_temps) / len(min_temps)) if min_temps else None,
        "avg_max_gust": (sum(gusts) / len(gusts)) if gusts else None,
    }


def compute_extremes(city_data: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Identify hottest/coldest/windiest/wettest, largest swing, island contrast."""
    hottest = _extreme_group(
        _cities_with_metric(city_data, "temperature_2m_max"), highest=True
    )
    coldest = _extreme_group(
        _cities_with_metric(city_data, "temperature_2m_min"), highest=False
    )
    windiest = _extreme_group(
        _cities_with_metric(city_data, "wind_gusts_10m_max"), highest=True
    )
    wettest = _extreme_group(
        _cities_with_metric(city_data, "precipitation_sum"), highest=True
    )

    swings: list[tuple[str, float]] = []
    for name, entry in city_data.items():
        max_t = _first_day_value(entry, "temperature_2m_max")
        min_t = _first_day_value(entry, "temperature_2m_min")
        if max_t is not None and min_t is not None:
            swings.append((name, max_t - min_t))

    largest_swing: dict[str, Any] | None = None
    if swings:
        best_name, best_value = max(swings, key=lambda item: item[1])
        largest_swing = {"city": best_name, "value": best_value}

    return {
        "hottest": hottest,
        "coldest": coldest,
        "windiest": windiest,
        "wettest": wettest,
        "largest_swing": largest_swing,
        "island_contrast": {
            "north": _island_avg(city_data, "north"),
            "south": _island_avg(city_data, "south"),
        },
    }
