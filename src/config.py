"""Weather Pulse NZ configuration constants and city definitions."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class CityConfig:
    name: str
    latitude: float
    longitude: float
    island: str  # "north" or "south"


WATCHED_CITIES: list[CityConfig] = [
    CityConfig("Auckland", -36.85, 174.76, "north"),
    CityConfig("Hamilton", -37.79, 175.28, "north"),
    CityConfig("Tauranga", -37.69, 176.17, "north"),
    CityConfig("Wellington", -41.29, 174.78, "north"),
    CityConfig("Nelson", -41.27, 173.28, "south"),
    CityConfig("Christchurch", -43.53, 172.64, "south"),
    CityConfig("Queenstown", -45.03, 168.66, "south"),
    CityConfig("Dunedin", -45.87, 170.50, "south"),
]

# Thresholds
WIND_NOTABLE_THRESHOLD_KMH = 40
AQI_WATCH_THRESHOLD = 100
AQI_UNHEALTHY_THRESHOLD = 150
DELTA_TEMP_THRESHOLD_C = 5.0
DELTA_AQI_THRESHOLD = 30

# Timeouts (seconds)
API_TIMEOUT_SECONDS = 10
BEDROCK_TIMEOUT_SECONDS = 30
SLACK_TIMEOUT_SECONDS = 10

# AWS Config (env overrides for deployed resources)
AWS_REGION = os.environ.get("AWS_REGION", "ap-southeast-2")
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "weather-pulse-state")
S3_BUCKET = os.environ.get("S3_BUCKET", "weather-pulse-reports")
SNS_TOPIC_ARN_ENV = "SNS_TOPIC_ARN"
SSM_SLACK_WEBHOOK_PARAM = os.environ.get(
    "SSM_SLACK_WEBHOOK_PARAM", "/weather-pulse/slack-webhook"
)
BEDROCK_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0"
)

REPORT_PRESIGN_EXPIRES_SECONDS = int(
    os.environ.get("REPORT_PRESIGN_EXPIRES_SECONDS", str(12 * 60 * 60))
)
HTML_REPORT_KEY = "reports/latest.html"
# Optional direct override; otherwise Lambda reads SSM_REPORT_LINK_PARAM.
REPORT_LINK_URL = os.environ.get("REPORT_LINK_URL", "").rstrip("/")
SSM_REPORT_LINK_PARAM = os.environ.get(
    "SSM_REPORT_LINK_PARAM", "/weather-pulse/report-link-url"
)

FORECAST_API_BASE = "https://api.open-meteo.com/v1/forecast"
AQI_API_BASE = "https://air-quality-api.open-meteo.com/v1/air-quality"
SNAPSHOT_PK = "latest_snapshot"
