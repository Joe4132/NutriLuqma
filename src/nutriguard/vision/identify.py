"""Food identification adapter (P2-02).

Public entry point is `identify_food`, which picks a backing implementation
behind the `FoodIdentifier` protocol:

- `FixtureIdentifier` (default): deterministic JSON lookup, zero network
  calls. Used in tests, CI, and this sandbox.
- `BedrockVisionIdentifier`: calls a Bedrock vision model via boto3. Gated
  behind `NUTRIGUARD_VISION_BACKEND=bedrock` so it is never accidentally
  invoked; boto3 client construction is isolated in `_bedrock.py` so tests
  can mock it without touching real AWS.

Neither implementation invents nutrition or portion data - they only ever
populate `label`, `identification_confidence`, `bbox`, and `source` on
`FoodItem`; `grams`/`portion_is_approximate` are left at their domain
defaults for the portion-estimation step (P2-03) to fill in.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal, Protocol

from nutriguard.domain.models import FoodItem
from nutriguard.vision import _bedrock

# Environment variable that gates the real Bedrock backend. Any other value
# (including unset) means "do not attempt real AWS calls".
_VISION_BACKEND_ENV_VAR = "NUTRIGUARD_VISION_BACKEND"

Backend = Literal["fixture", "bedrock"]


class FoodIdentifier(Protocol):
    """Swappable interface for turning an image into identified food items."""

    def identify(self, image_path: str) -> list[FoodItem]:
        """Return the food items identified in the image at `image_path`."""
        ...


class FixtureIdentifier:
    """Default identifier: looks up a deterministic fixture JSON mapping.

    The fixture file maps an image filename (or full path) to a list of
    food-item dicts. Matching is tried on the exact key first, then on the
    path's filename, so callers can pass either a bare filename or a full
    path to a file that happens to share that name.
    """

    def __init__(self, fixtures_path: str | Path) -> None:
        self._fixtures_path = Path(fixtures_path)
        with self._fixtures_path.open(encoding="utf-8") as f:
            self._fixtures: dict[str, list[dict[str, Any]]] = json.load(f)

    def identify(self, image_path: str) -> list[FoodItem]:
        """Look up `image_path` (or its filename) in the fixture mapping."""
        key = image_path if image_path in self._fixtures else Path(image_path).name
        if key not in self._fixtures:
            raise KeyError(
                f"No fixture entry for '{image_path}' in {self._fixtures_path}"
            )
        return [
            FoodItem(
                label=entry["label"],
                identification_confidence=entry["identification_confidence"],
                bbox=tuple(entry["bbox"]) if entry.get("bbox") is not None else None,
                source="fixture",
            )
            for entry in self._fixtures[key]
        ]


class BedrockVisionIdentifier:
    """Real identifier backed by a Bedrock vision model (Claude/Nova).

    Gated behind `NUTRIGUARD_VISION_BACKEND=bedrock` at construction time so
    it can never be instantiated by accident. The boto3 client is injected
    (or built lazily via `_bedrock.build_client`) so tests can supply a
    mock and never hit real AWS.
    """

    def __init__(self, client: Any | None = None) -> None:
        if os.environ.get(_VISION_BACKEND_ENV_VAR) != "bedrock":
            raise RuntimeError(
                f"BedrockVisionIdentifier requires {_VISION_BACKEND_ENV_VAR}=bedrock"
            )
        self._client = client if client is not None else _bedrock.build_client()

    def identify(self, image_path: str) -> list[FoodItem]:
        """Invoke the Bedrock vision model and parse its response into FoodItems."""
        raw_items = _bedrock.invoke_vision_model(self._client, image_path)
        return [
            FoodItem(
                label=item["label"],
                identification_confidence=item["identification_confidence"],
                bbox=tuple(item["bbox"]) if item.get("bbox") is not None else None,
                source="bedrock_vision",
            )
            for item in raw_items
        ]


def _default_fixtures_path() -> Path:
    """Repo-relative path to the identify fixtures file."""
    return Path(__file__).resolve().parents[3] / "fixtures" / "identify_fixtures.json"


def identify_food(image_path: str, backend: Backend = "fixture") -> list[FoodItem]:
    """Identify food items in an image using the requested backend.

    Args:
        image_path: Path to the image file (or, for the fixture backend
            only, a bare filename matching a fixture key).
        backend: "fixture" (default, no network calls) or "bedrock" (real
            Bedrock vision call, requires NUTRIGUARD_VISION_BACKEND=bedrock).

    Returns:
        A list of `FoodItem` with confidence in [0.0, 1.0].

    Raises:
        ValueError: if `backend` is not a recognized value.
        RuntimeError: if backend="bedrock" but the env gate is not set.
        KeyError: if backend="fixture" and `image_path` has no fixture entry.
    """
    if backend == "fixture":
        identifier: FoodIdentifier = FixtureIdentifier(_default_fixtures_path())
        return identifier.identify(image_path)
    if backend == "bedrock":
        if os.environ.get(_VISION_BACKEND_ENV_VAR) != "bedrock":
            raise RuntimeError(
                f"backend='bedrock' requires {_VISION_BACKEND_ENV_VAR}=bedrock"
            )
        identifier = BedrockVisionIdentifier()
        return identifier.identify(image_path)
    raise ValueError(f"Unknown backend: {backend!r}")
