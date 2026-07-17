"""Short public report / asset link base (Lambda Function URL)."""

from __future__ import annotations

import logging
from functools import lru_cache

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from src.config import AWS_REGION, REPORT_LINK_URL, SSM_REPORT_LINK_PARAM

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_from_ssm() -> str:
    try:
        client = boto3.client("ssm", region_name=AWS_REGION)
        value = client.get_parameter(Name=SSM_REPORT_LINK_PARAM)["Parameter"]["Value"]
        return str(value).rstrip("/")
    except (ClientError, BotoCoreError, KeyError, TypeError) as exc:
        logger.warning("Could not load report link from SSM: %s", exc)
        return ""


def report_link_base() -> str:
    """Return Function URL base with no trailing slash, or empty if unavailable."""
    if REPORT_LINK_URL:
        return REPORT_LINK_URL
    return _load_from_ssm()


def notification_report_url(*, fallback_presign) -> str:
    """Short /report URL when base is known; else call fallback_presign()."""
    base = report_link_base()
    if base:
        return f"{base}/report"
    return fallback_presign()
