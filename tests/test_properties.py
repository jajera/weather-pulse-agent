"""Property-based tests for Weather Pulse NZ computation and formatting."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from hypothesis import given, settings, strategies as st

from src.compute.deltas import compute_deltas
from src.compute.extremes import compute_extremes
from src.compute.thresholds import classify_thresholds
from src.config import CityConfig
from src.digest.bedrock import build_bedrock_prompt
from src.digest.template import generate_template_digest
from src.fetch.air_quality import build_aqi_url
from src.fetch.forecast import build_forecast_url
from src.output.s3_writer import render_html_report
from src.output.slack_poster import build_slack_payload
from src.output.sns_publisher import build_sns_message
from tests.conftest import sample_city, sample_payload

city_names = st.sampled_from(
    [
        "Auckland",
        "Hamilton",
        "Tauranga",
        "Wellington",
        "Nelson",
        "Christchurch",
        "Queenstown",
        "Dunedin",
    ]
)


@settings(max_examples=100)
@given(
    lat=st.floats(min_value=-47.0, max_value=-34.0, allow_nan=False, allow_infinity=False),
    lon=st.floats(min_value=166.0, max_value=179.0, allow_nan=False, allow_infinity=False),
    name=city_names,
)
def test_property_1_api_url_construction(lat, lon, name):
    # Feature: weather-pulse-nz, Property 1: API URL Construction
    city = CityConfig(name, lat, lon, "north")
    forecast_url = build_forecast_url(city)
    aqi_url = build_aqi_url(city)
    for token in (
        "temperature_2m_max",
        "temperature_2m_min",
        "wind_gusts_10m_max",
        "precipitation_sum",
        "weather_code",
        "temperature_2m",
        "precipitation",
        "forecast_days=3",
        "timezone=Pacific%2FAuckland",
    ):
        assert token in forecast_url
    assert str(lat) in forecast_url or f"{lat}" in forecast_url
    assert "us_aqi" in aqi_url
    assert "pm2_5" in aqi_url


@settings(max_examples=50)
@given(
    data=st.lists(
        st.tuples(
            city_names,
            st.floats(-5, 35, allow_nan=False, allow_infinity=False),
            st.floats(-10, 20, allow_nan=False, allow_infinity=False),
            st.floats(0, 100, allow_nan=False, allow_infinity=False),
            st.floats(0, 50, allow_nan=False, allow_infinity=False),
        ),
        min_size=1,
        max_size=8,
        unique_by=lambda item: item[0],
    )
)
def test_property_4_and_5_extremes_and_swing(data):
    # Feature: weather-pulse-nz, Property 4/5: Extreme City Identification / Swing
    cities = {}
    for name, max_t, min_t, gust, precip in data:
        if min_t > max_t:
            min_t, max_t = max_t, min_t
        island = (
            "north"
            if name in {"Auckland", "Hamilton", "Tauranga", "Wellington"}
            else "south"
        )
        cities[name] = sample_city(
            name, island=island, max_temp=max_t, min_temp=min_t, gust=gust, precip=precip
        )
    extremes = compute_extremes(cities)
    hottest = extremes["hottest"]
    assert hottest is not None
    max_value = max(c["forecast"]["daily"]["temperature_2m_max"][0] for c in cities.values())
    assert hottest["value"] == max_value
    assert set(hottest["cities"]) == {
        n
        for n, c in cities.items()
        if c["forecast"]["daily"]["temperature_2m_max"][0] == max_value
    }
    expected_swing = max(
        c["forecast"]["daily"]["temperature_2m_max"][0]
        - c["forecast"]["daily"]["temperature_2m_min"][0]
        for c in cities.values()
    )
    assert extremes["largest_swing"]["value"] == expected_swing


@settings(max_examples=50)
@given(
    gust=st.floats(0, 120, allow_nan=False, allow_infinity=False),
    aqi=st.one_of(st.none(), st.floats(0, 400, allow_nan=False, allow_infinity=False)),
)
def test_property_7_threshold_classification(gust, aqi):
    # Feature: weather-pulse-nz, Property 7: Threshold Classification
    cities = {"Auckland": sample_city("Auckland", gust=gust, us_aqi=aqi)}
    flags = classify_thresholds(cities)
    assert ("Auckland" in flags["wind_watchouts"]) == (gust >= 40)
    if aqi is None:
        assert "Auckland" not in flags["aqi_watch"]
        assert "Auckland" not in flags["aqi_unhealthy"]
    else:
        assert ("Auckland" in flags["aqi_unhealthy"]) == (aqi >= 150)
        assert ("Auckland" in flags["aqi_watch"]) == (100 <= aqi < 150)
    assert not (set(flags["aqi_watch"]) & set(flags["aqi_unhealthy"]))


@settings(max_examples=40)
@given(
    curr_gust=st.floats(0, 100, allow_nan=False, allow_infinity=False),
    prev_gust=st.floats(0, 100, allow_nan=False, allow_infinity=False),
    curr_temp=st.floats(-5, 35, allow_nan=False, allow_infinity=False),
    prev_temp=st.floats(-5, 35, allow_nan=False, allow_infinity=False),
    curr_aqi=st.floats(0, 300, allow_nan=False, allow_infinity=False),
    prev_aqi=st.floats(0, 300, allow_nan=False, allow_infinity=False),
)
def test_property_9_and_15_deltas_and_mood(
    curr_gust, prev_gust, curr_temp, prev_temp, curr_aqi, prev_aqi
):
    # Feature: weather-pulse-nz, Property 9/15: Delta Computation / Quiet Mood
    current = sample_payload(
        {
            "Auckland": sample_city(
                "Auckland", max_temp=curr_temp, gust=curr_gust, us_aqi=curr_aqi
            )
        }
    )
    previous = sample_payload(
        {
            "Auckland": sample_city(
                "Auckland", max_temp=prev_temp, gust=prev_gust, us_aqi=prev_aqi
            )
        }
    )
    delta = compute_deltas(current, previous)
    new_wind = "Auckland" in delta["new_alerts"]["wind_watchouts"]
    cleared_wind = "Auckland" in delta["cleared_alerts"]["wind_watchouts"]
    assert new_wind == (curr_gust >= 40 and prev_gust < 40)
    assert cleared_wind == (prev_gust >= 40 and curr_gust < 40)
    temp_hits = [c for c in delta["significant_temp_changes"] if c["city"] == "Auckland"]
    assert bool(temp_hits) == (abs(curr_temp - prev_temp) >= 5)
    aqi_hits = [c for c in delta["significant_aqi_changes"] if c["city"] == "Auckland"]
    assert bool(aqi_hits) == (abs(curr_aqi - prev_aqi) >= 30)
    if curr_aqi >= 150:
        assert delta["mood"] == "severe"
    elif (
        not any(delta["new_alerts"].values())
        and not any(delta["cleared_alerts"].values())
        and not delta["significant_temp_changes"]
        and not delta["significant_aqi_changes"]
    ):
        assert delta["mood"] == "quiet"


@settings(max_examples=40)
@given(mood=st.sampled_from(["quiet", "notable", "severe"]))
def test_property_10_template_fallback(mood):
    # Feature: weather-pulse-nz, Property 10: Template Fallback Produces Valid Executive_Brief
    payload = sample_payload()
    delta = compute_deltas(payload, payload)
    delta["mood"] = mood
    brief = generate_template_digest(payload, delta)
    assert len(brief["headline"]) <= 120
    assert 3 <= len(brief["bullets"]) <= 5
    assert brief["mood"] in {"quiet", "notable", "severe"}
    assert 0 <= len(brief["watchouts"]) <= 3


@settings(max_examples=20, deadline=None)
@given(st.just(None))
def test_property_11_12_13_14_prompt_html_sns_slack(_):
    # Feature: weather-pulse-nz, Property 11-14: prompt/html/sns/slack completeness
    from unittest.mock import patch

    payload = sample_payload()
    delta = compute_deltas(payload, payload)
    prompt = build_bedrock_prompt(payload, delta)
    assert "DATA PAYLOAD" in prompt
    assert "FORMATTING INSTRUCTIONS" in prompt
    assert "nz_extremes" in prompt or "extremes" in prompt.lower() or "nz_extremes" in prompt
    assert "threshold_flags" in prompt
    assert "headline" in prompt

    brief = generate_template_digest(payload, delta)
    with patch(
        "src.output.s3_writer.report_link_base",
        return_value="https://example.lambda-url.ap-southeast-2.on.aws",
    ):
        html = render_html_report(payload, delta, brief)
    for section in (
        "Executive Brief",
        "City Snapshot Board",
        "NZ Extremes",
        "Air Quality Watch",
        "Delta vs Last Run",
        "Sources and Attribution",
    ):
        assert section in html
    assert "Open-Meteo" in html and "CC BY 4.0" in html

    ts = datetime(2026, 7, 17, 6, 30, tzinfo=ZoneInfo("Pacific/Auckland"))
    report_url = "https://example.lambda-url.ap-southeast-2.on.aws/report"
    subject, body = build_sns_message(brief, ts, report_url)
    assert "Weather Pulse NZ" in subject
    assert "2026-07-17" in subject
    assert report_url in body

    slack = str(build_slack_payload(brief, ts, report_url))
    assert brief["headline"] in slack
    for bullet in brief["bullets"]:
        assert bullet in slack
    assert report_url in slack
