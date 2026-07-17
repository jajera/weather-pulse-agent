"""Example-based unit tests for Weather Pulse NZ."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from src.compute.deltas import compute_deltas, empty_delta_record
from src.config import WATCHED_CITIES
from src.digest import generate_digest
from src.digest.template import generate_template_digest
from src.fetch.air_quality import build_aqi_url
from src.fetch.forecast import build_forecast_url
from src.handler import AbortRunError, handler
from src.output.s3_writer import render_html_report
from src.output.slack_poster import build_slack_payload, post_slack
from src.output.sns_publisher import build_sns_message, publish_sns
from tests.conftest import sample_city, sample_payload


def test_watched_city_coordinates():
    expected = {
        "Auckland": (-36.85, 174.76),
        "Hamilton": (-37.79, 175.28),
        "Tauranga": (-37.69, 176.17),
        "Wellington": (-41.29, 174.78),
        "Nelson": (-41.27, 173.28),
        "Christchurch": (-43.53, 172.64),
        "Queenstown": (-45.03, 168.66),
        "Dunedin": (-45.87, 170.50),
    }
    assert len(WATCHED_CITIES) == 8
    for city in WATCHED_CITIES:
        assert (city.latitude, city.longitude) == expected[city.name]


def test_forecast_and_aqi_url_construction():
    city = WATCHED_CITIES[0]
    forecast_url = build_forecast_url(city)
    aqi_url = build_aqi_url(city)
    assert "temperature_2m_max" in forecast_url
    assert "wind_gusts_10m_max" in forecast_url
    assert "forecast_days=3" in forecast_url
    assert "forecast_hours=24" in forecast_url
    assert "timezone=Pacific%2FAuckland" in forecast_url
    assert str(city.latitude) in forecast_url
    assert "us_aqi" in aqi_url
    assert "pm2_5" in aqi_url


def test_all_forecasts_fail_aborts(monkeypatch):
    monkeypatch.setattr("src.handler.fetch_all_forecasts", lambda cities: {})
    monkeypatch.setattr("src.handler.fetch_all_air_quality", lambda cities: {})
    with pytest.raises(AbortRunError, match="No forecast data"):
        handler({}, None)


def test_first_run_and_comparison_unavailable_deltas():
    first = empty_delta_record(comparison_unavailable=False)
    assert first["is_first_run"] is True
    assert first["delta_note"] == "No prior data is available"
    assert first["mood"] == "quiet"
    unavailable = empty_delta_record(comparison_unavailable=True)
    assert unavailable["comparison_unavailable"] is True
    assert unavailable["delta_note"] == "Comparison was unavailable"

    unhealthy = sample_payload(
        {
            "Auckland": sample_city("Auckland", us_aqi=160),
            "Wellington": sample_city("Wellington", us_aqi=40),
        }
    )
    first_severe = empty_delta_record(
        comparison_unavailable=False, current_payload=unhealthy
    )
    assert first_severe["mood"] == "severe"
    assert compute_deltas(unhealthy, None)["mood"] == "severe"
    down_severe = empty_delta_record(
        comparison_unavailable=True, current_payload=unhealthy
    )
    assert down_severe["mood"] == "severe"


def test_quiet_delta_mood():
    current = sample_payload()
    previous = sample_payload()
    delta = compute_deltas(current, previous)
    assert delta["mood"] == "quiet"


def test_bedrock_fallback_to_template(monkeypatch):
    payload = sample_payload()
    delta = empty_delta_record()
    monkeypatch.setattr(
        "src.digest.generate_bedrock_digest", lambda *_args, **_kwargs: None
    )
    brief = generate_digest(payload, delta)
    assert 3 <= len(brief["bullets"]) <= 5
    assert brief["mood"] in {"quiet", "notable", "severe"}
    assert len(brief["headline"]) <= 120


def test_template_quiet_copy():
    payload = sample_payload()
    delta = empty_delta_record()
    delta["mood"] = "quiet"
    brief = generate_template_digest(payload, delta)
    assert "no major" in brief["headline"].lower()


def test_html_report_sections(monkeypatch):
    monkeypatch.setattr(
        "src.output.s3_writer.report_link_base",
        lambda: "https://abc.lambda-url.ap-southeast-2.on.aws",
    )
    payload = sample_payload()
    delta = empty_delta_record()
    brief = generate_template_digest(payload, delta)
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
    assert "Open-Meteo" in html
    assert "CC BY 4.0" in html
    assert "Auckland" in html
    assert 'rel="icon"' in html
    assert 'property="og:image"' in html
    assert "https://abc.lambda-url.ap-southeast-2.on.aws/og.jpg" in html
    assert "data:image/svg+xml," in html


def test_notification_report_url_uses_ssm_short_link(monkeypatch):
    from src.handler import handler, notification_report_url
    from src.report_link import _load_from_ssm

    _load_from_ssm.cache_clear()
    monkeypatch.setattr("src.report_link.REPORT_LINK_URL", "")
    monkeypatch.setattr(
        "src.report_link._load_from_ssm",
        lambda: "https://abc.lambda-url.ap-southeast-2.on.aws",
    )
    assert (
        notification_report_url()
        == "https://abc.lambda-url.ap-southeast-2.on.aws/report"
    )
    monkeypatch.setattr(
        "src.handler.read_html_report",
        lambda: "<!DOCTYPE html><html><body>proxy-ok</body></html>",
    )
    response = handler(
        {"requestContext": {"http": {"method": "GET"}}, "rawPath": "/report"},
        None,
    )
    assert response["statusCode"] == 200
    assert "text/html" in response["headers"]["Content-Type"]
    assert "proxy-ok" in response["body"]
    assert "AWSAccessKeyId" not in response.get("body", "")
    assert "Location" not in response.get("headers", {})

    favicon = handler(
        {"requestContext": {"http": {"method": "GET"}}, "rawPath": "/favicon.svg"},
        None,
    )
    assert favicon["statusCode"] == 200
    assert "image/svg+xml" in favicon["headers"]["Content-Type"]
    assert "Weather Pulse NZ" in favicon["body"]

    og = handler(
        {"requestContext": {"http": {"method": "GET"}}, "rawPath": "/og.jpg"},
        None,
    )
    assert og["statusCode"] == 200
    assert og["isBase64Encoded"] is True
    assert og["headers"]["Content-Type"] == "image/jpeg"
    assert len(og["body"]) > 100

    rejected = handler(
        {"requestContext": {"http": {"method": "POST"}}, "rawPath": "/report"},
        None,
    )
    assert rejected["statusCode"] == 405


def test_sns_message_format():
    brief = {
        "headline": "Test headline",
        "bullets": ["a", "b", "c"],
        "mood": "notable",
        "watchouts": ["Wellington winds"],
    }
    ts = datetime(2026, 7, 17, 6, 30, tzinfo=ZoneInfo("Pacific/Auckland"))
    report_url = "https://example.lambda-url.ap-southeast-2.on.aws/report"
    subject, body = build_sns_message(brief, ts, report_url)
    assert "Weather Pulse NZ" in subject
    assert "2026-07-17" in subject
    assert "notable" in subject
    assert "🟡 NOTABLE" in body
    assert "Test headline" in body
    assert report_url in body
    assert "Full HTML report:" in body


def test_sns_retry_once(monkeypatch):
    calls = {"n": 0}

    class FakeSNS:
        def publish(self, **_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("fail")
            return {}

    monkeypatch.setenv("SNS_TOPIC_ARN", "arn:aws:sns:ap-southeast-2:123:topic")
    monkeypatch.setattr(
        "src.output.sns_publisher.boto3.client", lambda *_a, **_k: FakeSNS()
    )
    monkeypatch.setattr("src.output.sns_publisher.time.sleep", lambda *_a, **_k: None)

    # ClientError expected by publish_sns — simulate with BotoCoreError-like path
    from botocore.exceptions import ClientError

    class FlakySNS:
        def publish(self, **_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ClientError(
                    {"Error": {"Code": "ServiceUnavailable", "Message": "x"}},
                    "Publish",
                )
            return {}

    calls["n"] = 0
    monkeypatch.setattr(
        "src.output.sns_publisher.boto3.client", lambda *_a, **_k: FlakySNS()
    )
    brief = {
        "headline": "h",
        "bullets": ["a", "b", "c"],
        "mood": "quiet",
        "watchouts": [],
    }
    ts = datetime(2026, 7, 17, 6, 30, tzinfo=ZoneInfo("Pacific/Auckland"))
    assert publish_sns(brief, ts, "https://example.com/report") is True
    assert calls["n"] == 2


def test_slack_payload_and_ssm_missing(monkeypatch):
    brief = {
        "headline": "Windy Wellington",
        "bullets": ["a", "b", "c"],
        "mood": "notable",
        "watchouts": ["Wellington: wind"],
    }
    ts = datetime(2026, 7, 17, 6, 30, tzinfo=ZoneInfo("Pacific/Auckland"))
    report_url = "https://example.com/reports/latest.html?X-Amz-Signature=abc"
    payload = build_slack_payload(brief, ts, report_url)
    assert payload["attachments"][0]["color"] == "#ecb22e"
    text_blob = str(payload)
    assert "Windy Wellington" in text_blob
    assert "Wellington: wind" in text_blob
    assert report_url in text_blob
    assert "NOTABLE" in text_blob

    quiet = build_slack_payload(
        {**brief, "mood": "quiet", "watchouts": []}, ts, report_url
    )
    assert quiet["attachments"][0]["color"] == "#2eb886"
    severe = build_slack_payload({**brief, "mood": "severe"}, ts, report_url)
    assert severe["attachments"][0]["color"] == "#e01e5a"

    monkeypatch.setattr(
        "src.output.slack_poster._get_webhook_url", lambda: None
    )
    assert post_slack(brief, ts, report_url) is False


def test_handler_quiet_run_still_delivers(monkeypatch):
    payload = sample_payload()
    city = next(iter(payload["cities"]))
    forecast = payload["cities"][city]["forecast"]
    aqi = payload["cities"][city]["air_quality"]

    monkeypatch.setattr(
        "src.handler.fetch_all_forecasts",
        lambda cities: {c.name: forecast for c in cities},
    )
    monkeypatch.setattr(
        "src.handler.fetch_all_air_quality",
        lambda cities: {c.name: aqi for c in cities},
    )
    monkeypatch.setattr("src.handler.state_store.get_snapshot", lambda: (None, False))
    monkeypatch.setattr("src.handler.state_store.put_snapshot", lambda *_a, **_k: True)
    monkeypatch.setattr(
        "src.handler.generate_digest",
        lambda *_a, **_k: {
            "headline": "Quiet run: no major change",
            "bullets": ["a", "b", "c"],
            "mood": "quiet",
            "watchouts": [],
        },
    )
    monkeypatch.setattr("src.handler.write_raw_json", lambda *_a, **_k: True)
    monkeypatch.setattr("src.handler.write_html_report", lambda *_a, **_k: True)
    monkeypatch.setattr(
        "src.handler.presign_report_url",
        lambda: "https://example.com/reports/latest.html?X-Amz-Signature=test",
    )
    writes = {"raw": 0, "html": 0, "sns": 0, "slack": 0}
    monkeypatch.setattr(
        "src.handler.write_raw_json",
        lambda *_a, **_k: writes.__setitem__("raw", writes["raw"] + 1) or True,
    )
    monkeypatch.setattr(
        "src.handler.write_html_report",
        lambda *_a, **_k: writes.__setitem__("html", writes["html"] + 1) or True,
    )
    monkeypatch.setattr(
        "src.handler.publish_sns",
        lambda *_a, **_k: writes.__setitem__("sns", writes["sns"] + 1) or True,
    )
    monkeypatch.setattr(
        "src.handler.post_slack",
        lambda *_a, **_k: writes.__setitem__("slack", writes["slack"] + 1) or True,
    )

    result = handler({}, None)
    assert result["statusCode"] == 200
    assert writes == {"raw": 1, "html": 1, "sns": 1, "slack": 1}


def test_handler_continues_when_s3_fails(monkeypatch):
    payload = sample_payload()
    city = next(iter(payload["cities"]))
    forecast = payload["cities"][city]["forecast"]
    aqi = payload["cities"][city]["air_quality"]

    monkeypatch.setattr(
        "src.handler.fetch_all_forecasts",
        lambda cities: {c.name: forecast for c in cities},
    )
    monkeypatch.setattr(
        "src.handler.fetch_all_air_quality",
        lambda cities: {c.name: aqi for c in cities},
    )
    monkeypatch.setattr("src.handler.state_store.get_snapshot", lambda: (None, False))
    monkeypatch.setattr("src.handler.state_store.put_snapshot", lambda *_a, **_k: True)
    monkeypatch.setattr(
        "src.handler.generate_digest",
        lambda *_a, **_k: {
            "headline": "h",
            "bullets": ["a", "b", "c"],
            "mood": "quiet",
            "watchouts": [],
        },
    )
    monkeypatch.setattr("src.handler.write_raw_json", lambda *_a, **_k: False)
    monkeypatch.setattr("src.handler.write_html_report", lambda *_a, **_k: False)
    monkeypatch.setattr(
        "src.handler.presign_report_url",
        lambda: "https://example.com/reports/latest.html?X-Amz-Signature=test",
    )
    notified = {"sns": False, "slack": False, "sns_url": "x", "slack_url": "x"}

    def _sns(_brief, _ts, report_url):
        notified["sns"] = True
        notified["sns_url"] = report_url
        return True

    def _slack(_brief, _ts, report_url):
        notified["slack"] = True
        notified["slack_url"] = report_url
        return True

    monkeypatch.setattr("src.handler.publish_sns", _sns)
    monkeypatch.setattr("src.handler.post_slack", _slack)
    result = handler({}, None)
    assert result["statusCode"] == 200
    assert notified["sns"] is True
    assert notified["slack"] is True
    assert notified["sns_url"] == ""
    assert notified["slack_url"] == ""
    assert result["report_url"] is None


def test_bedrock_mood_forced_from_delta():
    from src.digest.bedrock import _normalize_brief

    brief = _normalize_brief(
        {
            "headline": "Model wants quiet",
            "bullets": ["a", "b", "c"],
            "mood": "quiet",
            "watchouts": [],
        },
        {"mood": "severe"},
    )
    assert brief is not None
    assert brief["mood"] == "severe"


def test_sns_and_slack_omit_broken_report_link():
    brief = {
        "headline": "Test headline",
        "bullets": ["a", "b", "c"],
        "mood": "notable",
        "watchouts": [],
    }
    ts = datetime(2026, 7, 17, 6, 30, tzinfo=ZoneInfo("Pacific/Auckland"))
    _subject, body = build_sns_message(brief, ts, "")
    assert "unavailable this run" in body
    assert "http" not in body.split("Full HTML report:")[-1]

    slack = str(build_slack_payload(brief, ts, ""))
    assert "Report unavailable this run" in slack
    assert "View full report" not in slack


def test_severe_mood_when_unhealthy_aqi():
    cities = {
        "Auckland": sample_city("Auckland", us_aqi=160),
        "Wellington": sample_city("Wellington", us_aqi=40),
    }
    current = sample_payload(cities)
    previous = sample_payload(
        {
            "Auckland": sample_city("Auckland", us_aqi=160),
            "Wellington": sample_city("Wellington", us_aqi=40),
        }
    )
    delta = compute_deltas(current, previous)
    assert delta["mood"] == "severe"
