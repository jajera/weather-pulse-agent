"""Amazon Bedrock narrative digest generation."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from src.config import AWS_REGION, BEDROCK_MODEL_ID, BEDROCK_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a weather briefing writer for New Zealand. You narrate ONLY the facts "
    "provided. Do NOT invent data, severity levels, or thresholds beyond what is given."
)


def build_bedrock_prompt(
    run_payload: dict[str, Any], delta_record: dict[str, Any]
) -> str:
    """Build user prompt with data payload separated from formatting instructions."""
    data_payload = {
        "city_summaries": {
            name: {
                "island": entry.get("island"),
                "forecast_daily": (entry.get("forecast") or {}).get("daily"),
                "air_quality": entry.get("air_quality"),
            }
            for name, entry in (run_payload.get("cities") or {}).items()
        },
        "nz_extremes": run_payload.get("extremes"),
        "threshold_flags": run_payload.get("threshold_flags"),
        "delta_record": delta_record,
    }
    return (
        "## DATA PAYLOAD\n"
        f"{json.dumps(data_payload, default=str)}\n\n"
        "## FORMATTING INSTRUCTIONS\n"
        "Produce an Executive Brief with exactly this structure:\n"
        "1. HEADLINE: One sentence, 120 characters max, capturing the most notable condition\n"
        "2. BULLETS: 3 to 5 bullet points summarizing key conditions across NZ\n"
        "3. MOOD: One of: quiet, notable, severe (use the mood from the delta record)\n"
        "4. WATCHOUTS: Up to 3 top watchouts if any thresholds are exceeded (omit if none)\n\n"
        "Respond in valid JSON matching this schema:\n"
        '{"headline": str, "bullets": [str], "mood": str, "watchouts": [str]}'
    )


def _extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def _normalize_brief(raw: dict[str, Any], delta_record: dict[str, Any]) -> dict[str, Any] | None:
    headline = str(raw.get("headline") or "").strip()
    bullets = [str(b).strip() for b in (raw.get("bullets") or []) if str(b).strip()]
    # Mood is computed from thresholds/deltas — never trust model override.
    mood = str(delta_record.get("mood") or "notable").strip().lower()
    watchouts = [str(w).strip() for w in (raw.get("watchouts") or []) if str(w).strip()]

    if not headline or not (3 <= len(bullets) <= 5):
        return None
    if mood not in {"quiet", "notable", "severe"}:
        mood = "notable"
    return {
        "headline": headline[:120],
        "bullets": bullets[:5],
        "mood": mood,
        "watchouts": watchouts[:3],
    }


def generate_bedrock_digest(
    run_payload: dict[str, Any], delta_record: dict[str, Any]
) -> dict[str, Any] | None:
    """Invoke Bedrock Claude; return Executive_Brief or None on failure/timeout."""
    prompt = build_bedrock_prompt(run_payload, delta_record)
    client = boto3.client(
        "bedrock-runtime",
        region_name=AWS_REGION,
        config=Config(
            connect_timeout=BEDROCK_TIMEOUT_SECONDS,
            read_timeout=BEDROCK_TIMEOUT_SECONDS,
            retries={"max_attempts": 0},
        ),
    )
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        response = client.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body),
        )
        raw_body = json.loads(response["body"].read())
        content_blocks = raw_body.get("content") or []
        text = "".join(
            block.get("text", "")
            for block in content_blocks
            if block.get("type") == "text"
        )
        parsed = _extract_json(text)
        if not parsed:
            logger.error("Bedrock response was not valid JSON")
            return None
        return _normalize_brief(parsed, delta_record)
    except (BotoCoreError, ClientError, json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.error("Bedrock digest failed: %s", exc)
        return None
