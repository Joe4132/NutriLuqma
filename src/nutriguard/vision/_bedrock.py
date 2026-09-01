"""Thin boto3 seam for the Bedrock vision backend.

Split out from `identify.py` so the client construction (the only bit that
touches real AWS) can be monkeypatched/mocked independently in tests.
Nothing in this module is called unless `NUTRIGUARD_VISION_BACKEND=bedrock`.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

# Default model id for a Bedrock vision-capable model (Claude 3 Haiku).
# Kept as a module constant, not hardcoded inline, so it's easy to swap
# for another vision model (e.g. an Amazon Nova variant) without touching logic.
DEFAULT_MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"

_IDENTIFY_PROMPT = (
    "Identify each distinct food item visible in this image. Respond with "
    "ONLY a JSON array of objects, each with keys: label (string), "
    "identification_confidence (float 0.0-1.0), bbox (null or "
    "[x, y, w, h] normalized floats). No prose, no markdown fences."
)


def build_client() -> Any:
    """Construct a real boto3 bedrock-runtime client.

    Isolated in its own function so tests can monkeypatch this instead of
    hitting real AWS. Imports boto3 lazily so it is only required when the
    bedrock backend is actually used.
    """
    import boto3  # type: ignore[import-untyped]

    return boto3.client("bedrock-runtime", region_name="us-west-2")


def _guess_media_type(image_path: Path) -> str:
    """Best-effort content type from file extension. No invented defaults beyond jpeg."""
    suffix = image_path.suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix in (".jpg", ".jpeg"):
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/jpeg"


def invoke_vision_model(
    client: Any, image_path: str, model_id: str = DEFAULT_MODEL_ID
) -> list[dict[str, Any]]:
    """Send an image to a Bedrock vision model and return parsed food-item dicts.

    Returns raw dicts (not FoodItem) - the caller (identify.py) is
    responsible for validating/constructing the frozen domain type.
    """
    path = Path(image_path)
    image_bytes = path.read_bytes()
    encoded = base64.b64encode(image_bytes).decode("utf-8")

    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": _guess_media_type(path),
                            "data": encoded,
                        },
                    },
                    {"type": "text", "text": _IDENTIFY_PROMPT},
                ],
            }
        ],
    }

    response = client.invoke_model(
        modelId=model_id,
        body=json.dumps(request_body),
    )
    response_payload = json.loads(response["body"].read())
    raw_text = response_payload["content"][0]["text"]
    parsed: list[dict[str, Any]] = json.loads(raw_text)
    return parsed
