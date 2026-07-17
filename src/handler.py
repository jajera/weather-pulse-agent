"""Lambda entry point for Weather Pulse NZ."""

from __future__ import annotations

import base64
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from botocore.exceptions import BotoCoreError, ClientError

from src.branding import FAVICON_SVG, favicon_png_bytes, og_image_bytes
from src.compute.deltas import compute_deltas, empty_delta_record
from src.compute.extremes import compute_extremes
from src.compute.thresholds import classify_thresholds
from src.config import HTML_REPORT_KEY, WATCHED_CITIES
from src.digest import generate_digest
from src.fetch.air_quality import fetch_all_air_quality
from src.fetch.forecast import fetch_all_forecasts
from src.output.s3_writer import (
    presign_report_url,
    read_html_report,
    write_html_report,
    write_raw_json,
)
from src.output.slack_poster import post_slack
from src.output.sns_publisher import publish_sns
from src.report_link import notification_report_url as _notification_report_url
from src.state import dynamo as state_store

logger = logging.getLogger(__name__)
logging.getLogger().setLevel(logging.INFO)

_ASSET_CACHE_CONTROL = "public, max-age=86400"


class AbortRunError(RuntimeError):
    """Raised when the run cannot continue (e.g. no forecast data)."""


def build_city_data(
    forecasts: dict[str, dict[str, Any]],
    air_quality: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Assemble per-city entries from fetch results."""
    city_lookup = {city.name: city for city in WATCHED_CITIES}
    city_data: dict[str, dict[str, Any]] = {}

    for name, forecast in forecasts.items():
        city = city_lookup.get(name)
        if city is None:
            continue
        entry: dict[str, Any] = {
            "coordinates": {
                "latitude": city.latitude,
                "longitude": city.longitude,
            },
            "island": city.island,
            "forecast": forecast,
            "air_quality": air_quality.get(
                name, {"us_aqi": None, "pm2_5": None}
            ),
        }
        city_data[name] = entry
    return city_data


def _http_method(event: dict[str, Any] | None) -> str | None:
    """Return HTTP method for Function URL / API Gateway events; else None."""
    if not event:
        return None
    http = (event.get("requestContext") or {}).get("http") or {}
    method = http.get("method") or event.get("httpMethod")
    if not method:
        return None
    return str(method).upper()


def _request_path(event: dict[str, Any] | None) -> str:
    if not event:
        return "/"
    path = event.get("rawPath") or event.get("path") or "/"
    return str(path).split("?", 1)[0] or "/"


def _report_proxy_response() -> dict[str, Any]:
    """Serve latest HTML from S3 so the browser stays on the short Function URL."""
    try:
        body = read_html_report()
    except (ClientError, BotoCoreError, UnicodeDecodeError) as exc:
        logger.error("Failed to load report from S3: %s", exc)
        return {
            "statusCode": 502,
            "headers": {"Content-Type": "text/plain; charset=utf-8"},
            "body": "Report temporarily unavailable.",
        }
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-store",
        },
        "body": body,
        "isBase64Encoded": False,
    }


def _binary_response(body: bytes, content_type: str) -> dict[str, Any]:
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": content_type,
            "Cache-Control": _ASSET_CACHE_CONTROL,
        },
        "body": base64.b64encode(body).decode("ascii"),
        "isBase64Encoded": True,
    }


def _text_response(body: str, content_type: str) -> dict[str, Any]:
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": content_type,
            "Cache-Control": _ASSET_CACHE_CONTROL,
        },
        "body": body,
        "isBase64Encoded": False,
    }


def _method_not_allowed() -> dict[str, Any]:
    return {
        "statusCode": 405,
        "headers": {
            "Content-Type": "text/plain; charset=utf-8",
            "Allow": "GET",
        },
        "body": "Method Not Allowed",
    }


def _http_get_response(event: dict[str, Any] | None) -> dict[str, Any]:
    path = _request_path(event).rstrip("/") or "/"
    if path in {"/favicon.svg", "favicon.svg"}:
        return _text_response(FAVICON_SVG, "image/svg+xml; charset=utf-8")
    if path in {"/favicon.png", "/favicon.ico", "favicon.png", "favicon.ico"}:
        return _binary_response(favicon_png_bytes(), "image/png")
    if path in {"/og.jpg", "/og.jpeg", "/og.png", "og.jpg", "og.jpeg", "og.png"}:
        return _binary_response(og_image_bytes(), "image/jpeg")
    logger.info("Report link request → proxying %s", HTML_REPORT_KEY)
    return _report_proxy_response()


def notification_report_url() -> str:
    """Short Function URL when configured; otherwise a direct pre-signed URL."""
    return _notification_report_url(fallback_presign=presign_report_url)


def handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    """HTTP assets/report proxy (GET only), or run the daily pipeline."""
    method = _http_method(event)
    if method is not None:
        if method == "GET":
            return _http_get_response(event)
        logger.warning("Rejected HTTP %s on Function URL", method)
        return _method_not_allowed()

    run_timestamp = datetime.now(ZoneInfo("Pacific/Auckland"))
    logger.info("Weather Pulse NZ run starting at %s", run_timestamp.isoformat())

    with ThreadPoolExecutor(max_workers=2) as pool:
        forecast_future = pool.submit(fetch_all_forecasts, WATCHED_CITIES)
        aqi_future = pool.submit(fetch_all_air_quality, WATCHED_CITIES)
        forecasts = forecast_future.result()
        air_quality = aqi_future.result()

    if not forecasts:
        raise AbortRunError("No forecast data obtained for any city")

    city_data = build_city_data(forecasts, air_quality)
    extremes = compute_extremes(city_data)
    threshold_flags = classify_thresholds(city_data)
    run_payload: dict[str, Any] = {
        "run_timestamp": run_timestamp.isoformat(),
        "cities": city_data,
        "extremes": extremes,
        "threshold_flags": threshold_flags,
    }

    previous, read_failed = state_store.get_snapshot()
    if read_failed:
        delta_record = empty_delta_record(
            comparison_unavailable=True,
            current_payload=run_payload,
        )
    elif previous is None:
        delta_record = empty_delta_record(
            comparison_unavailable=False,
            current_payload=run_payload,
        )
    else:
        delta_record = compute_deltas(run_payload, previous)

    state_store.put_snapshot(run_payload)

    executive_brief = generate_digest(run_payload, delta_record)

    write_raw_json(run_payload, run_timestamp)
    html_ok = write_html_report(run_payload, delta_record, executive_brief)
    report_url = notification_report_url() if html_ok else ""
    if not html_ok:
        logger.error("HTML report write failed; omitting report link from notifications")

    publish_sns(executive_brief, run_timestamp, report_url)
    post_slack(executive_brief, run_timestamp, report_url)

    logger.info(
        "Weather Pulse NZ run complete mood=%s", executive_brief.get("mood")
    )
    return {
        "statusCode": 200,
        "run_timestamp": run_timestamp.isoformat(),
        "mood": executive_brief.get("mood"),
        "report_url": report_url or None,
    }
