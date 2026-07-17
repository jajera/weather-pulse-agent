"""Delta comparison against the previous run snapshot."""

from __future__ import annotations

from typing import Any

from src.compute.thresholds import classify_thresholds
from src.config import DELTA_AQI_THRESHOLD, DELTA_TEMP_THRESHOLD_C


def _empty_alerts() -> dict[str, list[str]]:
    return {"wind_watchouts": [], "aqi_watch": [], "aqi_unhealthy": []}


def empty_delta_record(
    *,
    comparison_unavailable: bool = False,
    current_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an empty Delta_Record used for first-run or failed comparison.

    Mood still reflects current unhealthy AQI so day-one / Dynamo-down runs
    are not stuck on quiet when air quality is severe.
    """
    mood = "quiet"
    if current_payload is not None and _alert_sets(current_payload)["aqi_unhealthy"]:
        mood = "severe"

    if comparison_unavailable:
        return {
            "is_first_run": False,
            "comparison_unavailable": True,
            "delta_note": "Comparison was unavailable",
            "new_alerts": _empty_alerts(),
            "cleared_alerts": _empty_alerts(),
            "significant_temp_changes": [],
            "significant_aqi_changes": [],
            "mood": mood,
        }
    return {
        "is_first_run": True,
        "comparison_unavailable": False,
        "delta_note": "No prior data is available",
        "new_alerts": _empty_alerts(),
        "cleared_alerts": _empty_alerts(),
        "significant_temp_changes": [],
        "significant_aqi_changes": [],
        "mood": mood,
    }


def _alert_sets(payload: dict[str, Any]) -> dict[str, set[str]]:
    flags = payload.get("threshold_flags")
    if not flags:
        flags = classify_thresholds(payload.get("cities") or {})
    return {
        "wind_watchouts": set(flags.get("wind_watchouts") or []),
        "aqi_watch": set(flags.get("aqi_watch") or []),
        "aqi_unhealthy": set(flags.get("aqi_unhealthy") or []),
    }


def _first_day_max_temp(payload: dict[str, Any], city: str) -> float | None:
    cities = payload.get("cities") or {}
    entry = cities.get(city) or {}
    daily = ((entry.get("forecast") or {}).get("daily") or {})
    values = daily.get("temperature_2m_max") or []
    if not values or values[0] is None:
        return None
    try:
        return float(values[0])
    except (TypeError, ValueError):
        return None


def _us_aqi(payload: dict[str, Any], city: str) -> float | None:
    cities = payload.get("cities") or {}
    entry = cities.get(city) or {}
    value = (entry.get("air_quality") or {}).get("us_aqi")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _classify_mood(
    current_flags: dict[str, set[str]],
    new_alerts: dict[str, list[str]],
    cleared_alerts: dict[str, list[str]],
    temp_changes: list[dict[str, Any]],
    aqi_changes: list[dict[str, Any]],
) -> str:
    if current_flags["aqi_unhealthy"]:
        return "severe"
    no_new = all(not values for values in new_alerts.values())
    no_cleared = all(not values for values in cleared_alerts.values())
    if no_new and no_cleared and not temp_changes and not aqi_changes:
        return "quiet"
    return "notable"


def compute_deltas(
    current_payload: dict[str, Any],
    previous_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compare current Run_Payload to previous snapshot."""
    if previous_payload is None:
        return empty_delta_record(
            comparison_unavailable=False,
            current_payload=current_payload,
        )

    current_flags = _alert_sets(current_payload)
    previous_flags = _alert_sets(previous_payload)

    new_alerts = {
        key: sorted(current_flags[key] - previous_flags[key])
        for key in ("wind_watchouts", "aqi_watch", "aqi_unhealthy")
    }
    cleared_alerts = {
        key: sorted(previous_flags[key] - current_flags[key])
        for key in ("wind_watchouts", "aqi_watch", "aqi_unhealthy")
    }

    city_names = set((current_payload.get("cities") or {}).keys()) | set(
        (previous_payload.get("cities") or {}).keys()
    )

    significant_temp_changes: list[dict[str, Any]] = []
    significant_aqi_changes: list[dict[str, Any]] = []

    for city in sorted(city_names):
        current_temp = _first_day_max_temp(current_payload, city)
        previous_temp = _first_day_max_temp(previous_payload, city)
        if current_temp is not None and previous_temp is not None:
            delta = current_temp - previous_temp
            if abs(delta) >= DELTA_TEMP_THRESHOLD_C:
                significant_temp_changes.append(
                    {
                        "city": city,
                        "previous": previous_temp,
                        "current": current_temp,
                        "delta": delta,
                    }
                )

        current_aqi = _us_aqi(current_payload, city)
        previous_aqi = _us_aqi(previous_payload, city)
        if current_aqi is not None and previous_aqi is not None:
            delta = current_aqi - previous_aqi
            if abs(delta) >= DELTA_AQI_THRESHOLD:
                significant_aqi_changes.append(
                    {
                        "city": city,
                        "previous": previous_aqi,
                        "current": current_aqi,
                        "delta": delta,
                    }
                )

    mood = _classify_mood(
        current_flags,
        new_alerts,
        cleared_alerts,
        significant_temp_changes,
        significant_aqi_changes,
    )

    return {
        "is_first_run": False,
        "comparison_unavailable": False,
        "delta_note": None,
        "new_alerts": new_alerts,
        "cleared_alerts": cleared_alerts,
        "significant_temp_changes": significant_temp_changes,
        "significant_aqi_changes": significant_aqi_changes,
        "mood": mood,
    }
