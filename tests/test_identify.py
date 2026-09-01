"""Tests for the food identification adapter (P2-02).

Covers both backends behind `identify_food`:
- FixtureIdentifier: deterministic JSON lookup, no network calls.
- BedrockVisionIdentifier: boto3 client is always mocked here, never real.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from nutriguard.domain.models import FoodItem
from nutriguard.vision.identify import (
    BedrockVisionIdentifier,
    FixtureIdentifier,
    identify_food,
)

FIXTURES_PATH = Path(__file__).parent.parent / "fixtures" / "identify_fixtures.json"


# --------------------------------------------------------------------------
# FixtureIdentifier
# --------------------------------------------------------------------------


def test_fixture_identifier_returns_food_items_for_known_image() -> None:
    identifier = FixtureIdentifier(FIXTURES_PATH)
    items = identifier.identify("chicken_rice_bowl.jpg")
    assert len(items) == 2
    assert all(isinstance(item, FoodItem) for item in items)
    assert all(0.0 <= item.identification_confidence <= 1.0 for item in items)
    assert all(item.source == "fixture" for item in items)


def test_fixture_identifier_matches_by_filename_when_full_path_given() -> None:
    identifier = FixtureIdentifier(FIXTURES_PATH)
    items = identifier.identify("/some/tmp/dir/chicken_rice_bowl.jpg")
    assert len(items) == 2


def test_fixture_identifier_raises_for_unknown_image() -> None:
    identifier = FixtureIdentifier(FIXTURES_PATH)
    with pytest.raises(KeyError):
        identifier.identify("does_not_exist.jpg")


def test_low_confidence_peanut_sauce_fixture_entry() -> None:
    identifier = FixtureIdentifier(FIXTURES_PATH)
    items = identifier.identify("pad_thai_with_peanut_sauce.jpg")
    peanut_items = [item for item in items if "peanut" in item.label.lower()]
    assert len(peanut_items) == 1
    assert peanut_items[0].identification_confidence < 0.5


# --------------------------------------------------------------------------
# identify_food public entry point
# --------------------------------------------------------------------------


def test_identify_food_default_backend_is_fixture() -> None:
    items = identify_food("garden_salad.jpg")
    assert len(items) == 1
    assert items[0].label == "mixed greens salad"
    assert items[0].source == "fixture"


def test_identify_food_bedrock_backend_requires_env_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NUTRIGUARD_VISION_BACKEND", raising=False)
    with pytest.raises(RuntimeError):
        identify_food("anything.jpg", backend="bedrock")


def test_identify_food_rejects_unknown_backend() -> None:
    with pytest.raises(ValueError, match="Unknown backend"):
        identify_food("anything.jpg", backend="not-a-real-backend")  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# BedrockVisionIdentifier (mocked boto3 client, no real AWS calls)
# --------------------------------------------------------------------------


def test_bedrock_vision_identifier_rejects_construction_without_env_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NUTRIGUARD_VISION_BACKEND", raising=False)
    with pytest.raises(RuntimeError):
        BedrockVisionIdentifier(client=MagicMock())


def test_bedrock_vision_identifier_with_mocked_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("NUTRIGUARD_VISION_BACKEND", "bedrock")

    mock_client = MagicMock()
    response_payload = {
        "content": [
            {
                "text": json.dumps(
                    [
                        {
                            "label": "steamed broccoli",
                            "identification_confidence": 0.77,
                            "bbox": None,
                        }
                    ]
                )
            }
        ]
    }
    mock_body = MagicMock()
    mock_body.read.return_value = json.dumps(response_payload).encode("utf-8")
    mock_client.invoke_model.return_value = {"body": mock_body}

    image_path = tmp_path / "broccoli.jpg"
    image_path.write_bytes(b"fake-image-bytes")

    identifier = BedrockVisionIdentifier(client=mock_client)
    items = identifier.identify(str(image_path))

    assert len(items) == 1
    assert isinstance(items[0], FoodItem)
    assert items[0].label == "steamed broccoli"
    assert items[0].identification_confidence == pytest.approx(0.77)
    assert items[0].source == "bedrock_vision"
    mock_client.invoke_model.assert_called_once()


def test_identify_food_with_bedrock_backend_and_monkeypatched_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """identify_food("...", backend="bedrock") should use a mocked client too."""
    monkeypatch.setenv("NUTRIGUARD_VISION_BACKEND", "bedrock")

    mock_client = MagicMock()
    response_payload = {
        "content": [
            {
                "text": json.dumps(
                    [{"label": "grilled salmon", "identification_confidence": 0.88, "bbox": None}]
                )
            }
        ]
    }
    mock_body = MagicMock()
    mock_body.read.return_value = json.dumps(response_payload).encode("utf-8")
    mock_client.invoke_model.return_value = {"body": mock_body}

    import nutriguard.vision._bedrock as bedrock_module

    monkeypatch.setattr(bedrock_module, "build_client", lambda: mock_client)

    image_path = tmp_path / "salmon.jpg"
    image_path.write_bytes(b"fake-image-bytes")

    items = identify_food(str(image_path), backend="bedrock")

    assert len(items) == 1
    assert items[0].label == "grilled salmon"
    assert items[0].source == "bedrock_vision"
