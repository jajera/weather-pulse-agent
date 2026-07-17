"""Template-based Executive_Brief fallback."""

from __future__ import annotations

from typing import Any


def _fmt_cities(extreme: dict[str, Any] | None) -> str:
    if not extreme:
        return "n/a"
    cities = ", ".join(extreme.get("cities") or [])
    value = extreme.get("value")
    return f"{cities} ({value})"


def generate_template_digest(
    run_payload: dict[str, Any], delta_record: dict[str, Any]
) -> dict[str, Any]:
    """Always produce a valid Executive_Brief from structured facts."""
    mood = str(delta_record.get("mood") or "notable")
    extremes = run_payload.get("extremes") or {}
    flags = run_payload.get("threshold_flags") or {}
    contrast = extremes.get("island_contrast") or {}
    north = contrast.get("north") or {}
    south = contrast.get("south") or {}

    if mood == "quiet":
        headline = "Quiet run: no major weather or air-quality change across NZ"
        bullets = [
            "No new or cleared wind/AQI alerts since the last run",
            "City temperature and US AQI moves stayed below notable thresholds",
            "Full city snapshot and extremes are available in the HTML report",
        ]
        if extremes.get("hottest"):
            bullets.append(f"Hottest today: {_fmt_cities(extremes.get('hottest'))}")
        if extremes.get("coldest"):
            bullets.append(f"Coldest today: {_fmt_cities(extremes.get('coldest'))}")
    else:
        windiest = extremes.get("windiest")
        hottest = extremes.get("hottest")
        coldest = extremes.get("coldest")
        parts = []
        if windiest:
            parts.append(f"{', '.join(windiest.get('cities') or [])} gusts {windiest.get('value')} km/h")
        if coldest:
            parts.append(f"coldest {_fmt_cities(coldest)}")
        if hottest:
            parts.append(f"hottest {_fmt_cities(hottest)}")
        headline = "; ".join(parts) if parts else "Weather Pulse NZ daily briefing"
        headline = headline[:120]

        bullets = []
        if hottest:
            bullets.append(f"Hottest: {_fmt_cities(hottest)}")
        if coldest:
            bullets.append(f"Coldest: {_fmt_cities(coldest)}")
        if windiest:
            bullets.append(f"Windiest: {_fmt_cities(windiest)}")
        wettest = extremes.get("wettest")
        if wettest:
            bullets.append(f"Wettest: {_fmt_cities(wettest)}")
        if north.get("avg_max_temp") is not None and south.get("avg_max_temp") is not None:
            bullets.append(
                "Island contrast max temps: "
                f"North {north['avg_max_temp']:.1f}°C vs South {south['avg_max_temp']:.1f}°C"
            )
        if delta_record.get("significant_temp_changes"):
            change = delta_record["significant_temp_changes"][0]
            bullets.append(
                f"{change['city']} max temp changed by {change['delta']:+.1f}°C"
            )
        if delta_record.get("significant_aqi_changes"):
            change = delta_record["significant_aqi_changes"][0]
            bullets.append(
                f"{change['city']} US AQI changed by {change['delta']:+.0f}"
            )
        while len(bullets) < 3:
            bullets.append("See the HTML report for the full city snapshot board")
        bullets = bullets[:5]

    watchouts: list[str] = []
    for city in flags.get("aqi_unhealthy") or []:
        watchouts.append(f"{city}: unhealthy air quality (US AQI >= 150)")
    for city in flags.get("aqi_watch") or []:
        watchouts.append(f"{city}: air quality watch (US AQI 100-149)")
    for city in flags.get("wind_watchouts") or []:
        watchouts.append(f"{city}: wind watchout (gusts >= 40 km/h)")
    watchouts = watchouts[:3]

    return {
        "headline": headline[:120],
        "bullets": bullets[:5],
        "mood": mood if mood in {"quiet", "notable", "severe"} else "notable",
        "watchouts": watchouts,
    }
