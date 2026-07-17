"""Slack Incoming Webhook delivery."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from src.config import (
    AWS_REGION,
    SLACK_TIMEOUT_SECONDS,
    SSM_SLACK_WEBHOOK_PARAM,
)

logger = logging.getLogger(__name__)

# Attachment sidebar colors (Slack classic attachments)
MOOD_COLORS = {
    "quiet": "#2eb886",    # green
    "notable": "#ecb22e",  # amber
    "severe": "#e01e5a",   # red
}
MOOD_EMOJI = {
    "quiet": ":large_green_circle:",
    "notable": ":large_yellow_circle:",
    "severe": ":red_circle:",
}


def build_slack_payload(
    executive_brief: dict[str, Any],
    run_timestamp: datetime,
    report_url: str,
) -> dict[str, Any]:
    """Build Slack payload with mood-colored attachment sidebar."""
    run_date = run_timestamp.strftime("%Y-%m-%d")
    mood = str(executive_brief.get("mood") or "notable").lower()
    color = MOOD_COLORS.get(mood, MOOD_COLORS["notable"])
    mood_emoji = MOOD_EMOJI.get(mood, MOOD_EMOJI["notable"])

    bullets = "\n".join(f"• {b}" for b in (executive_brief.get("bullets") or []))
    watchouts = executive_brief.get("watchouts") or []
    if watchouts:
        watchout_text = (
            ":warning: *Watchouts*\n" + "\n".join(f"• {w}" for w in watchouts)
        )
    else:
        watchout_text = ":white_check_mark: *Watchouts*\n• None"

    if report_url:
        report_text = f"Mood: `{mood}` | <{report_url}|View full report>"
    else:
        report_text = f"Mood: `{mood}` | Report unavailable this run"

    return {
        "attachments": [
            {
                "color": color,
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"Weather Pulse NZ — {run_date}",
                        },
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"{mood_emoji} *{mood.upper()}*  |  "
                                f"*{executive_brief.get('headline')}*"
                            ),
                        },
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": bullets},
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": watchout_text},
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": report_text,
                            }
                        ],
                    },
                ],
            }
        ]
    }


def _get_webhook_url() -> str | None:
    try:
        client = boto3.client("ssm", region_name=AWS_REGION)
        response = client.get_parameter(
            Name=SSM_SLACK_WEBHOOK_PARAM, WithDecryption=True
        )
        return response["Parameter"]["Value"]
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in {"ParameterNotFound", "AccessDeniedException"}:
            logger.warning("Slack webhook SSM parameter not found or inaccessible")
            return None
        logger.error("SSM GetParameter failed: %s", exc)
        return None
    except (BotoCoreError, KeyError, TypeError) as exc:
        logger.error("SSM GetParameter failed: %s", exc)
        return None


def _post_once(webhook_url: str, payload: dict[str, Any]) -> bool:
    request = Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=SLACK_TIMEOUT_SECONDS) as response:
            return 200 <= response.status < 300
    except HTTPError as exc:
        logger.error("Slack POST HTTP error: %s", exc.code)
        return False
    except (URLError, TimeoutError, OSError) as exc:
        logger.error("Slack POST failed: %s", exc)
        return False


def post_slack(
    executive_brief: dict[str, Any],
    run_timestamp: datetime,
    report_url: str,
) -> bool:
    """Post digest to Slack with one retry. Skip if webhook missing."""
    webhook_url = _get_webhook_url()
    if not webhook_url:
        return False

    payload = build_slack_payload(executive_brief, run_timestamp, report_url)
    if _post_once(webhook_url, payload):
        return True
    logger.warning("Retrying Slack POST once")
    return _post_once(webhook_url, payload)
