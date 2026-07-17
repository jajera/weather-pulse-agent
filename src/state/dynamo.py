"""DynamoDB last-run snapshot store."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from src.config import AWS_REGION, DYNAMODB_TABLE, SNAPSHOT_PK

logger = logging.getLogger(__name__)


def get_snapshot() -> tuple[dict[str, Any] | None, bool]:
    """Read the latest Run_Payload snapshot.

    Returns:
        (payload, failed)
        - (dict, False) when an item exists
        - (None, False) when no prior snapshot exists
        - (None, True) when the read fails
    """
    try:
        client = boto3.client("dynamodb", region_name=AWS_REGION)
        response = client.get_item(
            TableName=DYNAMODB_TABLE,
            Key={"pk": {"S": SNAPSHOT_PK}},
        )
        item = response.get("Item")
        if not item:
            return None, False
        payload_raw = item.get("payload", {}).get("S")
        if not payload_raw:
            return None, False
        return json.loads(payload_raw), False
    except (BotoCoreError, ClientError, json.JSONDecodeError, TypeError) as exc:
        logger.error("DynamoDB get_snapshot failed: %s", exc)
        return None, True


def put_snapshot(run_payload: dict[str, Any]) -> bool:
    """Persist the full Run_Payload as the latest snapshot."""
    try:
        client = boto3.client("dynamodb", region_name=AWS_REGION)
        ttl = int(time.time()) + 7 * 24 * 60 * 60
        client.put_item(
            TableName=DYNAMODB_TABLE,
            Item={
                "pk": {"S": SNAPSHOT_PK},
                "run_timestamp": {"S": str(run_payload.get("run_timestamp", ""))},
                "payload": {"S": json.dumps(run_payload, default=str)},
                "ttl": {"N": str(ttl)},
            },
        )
        return True
    except (BotoCoreError, ClientError, TypeError) as exc:
        logger.error("DynamoDB put_snapshot failed: %s", exc)
        return False
