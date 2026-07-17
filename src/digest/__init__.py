"""Digest generation: Bedrock with template fallback."""

from __future__ import annotations

import logging
from typing import Any

from src.digest.bedrock import generate_bedrock_digest
from src.digest.template import generate_template_digest

logger = logging.getLogger(__name__)


def generate_digest(
    run_payload: dict[str, Any], delta_record: dict[str, Any]
) -> dict[str, Any]:
    """Try Bedrock first; fall back to template on failure."""
    brief = generate_bedrock_digest(run_payload, delta_record)
    if brief is not None:
        logger.info("Digest generated via Bedrock")
        return brief
    logger.warning("Bedrock unavailable; using template digest fallback")
    return generate_template_digest(run_payload, delta_record)
