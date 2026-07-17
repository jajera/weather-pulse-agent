"""SNS email digest publisher."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from src.config import AWS_REGION, SNS_TOPIC_ARN_ENV

logger = logging.getLogger(__name__)

MOOD_BANNER = {
    "quiet": "🟢 QUIET",
    "notable": "🟡 NOTABLE",
    "severe": "🔴 SEVERE",
}


def build_sns_message(
    executive_brief: dict[str, Any],
    run_timestamp: datetime,
    report_url: str,
) -> tuple[str, str]:
    """Return (subject, body) for the SNS publish call."""
    run_date = run_timestamp.strftime("%Y-%m-%d")
    mood = str(executive_brief.get("mood") or "notable").lower()
    mood_label = MOOD_BANNER.get(mood, MOOD_BANNER["notable"])
    subject = f"Weather Pulse NZ — {run_date} ({mood})"

    bullets = "\n".join(
        f"   • {b}" for b in (executive_brief.get("bullets") or [])
    )
    watchouts = executive_brief.get("watchouts") or []
    if watchouts:
        watchout_block = "\n".join(f"   ⚠️  {w}" for w in watchouts)
    else:
        watchout_block = "   ✅ None"

    # Keep the URL on its own line so mail clients make one clean hyperlink.
    if report_url:
        report_block = f"📄  Full HTML report: {report_url}"
    else:
        report_block = "📄  Full HTML report: unavailable this run"

    body = f"""🌤️  Weather Pulse NZ — Daily Briefing
{'═' * 42}

{mood_label}

📌  {executive_brief.get('headline')}

────────────────────────────────────────
KEY POINTS
{bullets}

────────────────────────────────────────
WATCHOUTS
{watchout_block}

────────────────────────────────────────
{report_block}
"""
    return subject, body


def publish_sns(
    executive_brief: dict[str, Any],
    run_timestamp: datetime,
    report_url: str,
) -> bool:
    """Publish digest to SNS with one retry."""
    topic_arn = os.environ.get(SNS_TOPIC_ARN_ENV)
    if not topic_arn:
        logger.error("SNS topic ARN env %s is not set", SNS_TOPIC_ARN_ENV)
        return False

    subject, body = build_sns_message(executive_brief, run_timestamp, report_url)
    client = boto3.client("sns", region_name=AWS_REGION)

    for attempt in range(2):
        try:
            client.publish(TopicArn=topic_arn, Subject=subject, Message=body)
            return True
        except (BotoCoreError, ClientError) as exc:
            logger.error("SNS publish attempt %s failed: %s", attempt + 1, exc)
            if attempt == 0:
                time.sleep(2)
    return False
