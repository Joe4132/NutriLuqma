"""
P1-03 — SSM configuration loader tests.

Uses mocked boto3 SSM client — no real AWS calls.

Cases:
1. All parameters present → returns correct dict.
2. One parameter missing → ConfigurationError naming the missing param.
3. Second call uses cache (SSM client called only once).
4. invalidate_cache() clears the cache so next call hits SSM again.
5. SSM fails (ClientError) → env fallback used when env vars are set.
6. Both SSM and env fail → ConfigurationError.

Run: python -m pytest tests/test_config_ssm.py -v
"""

from __future__ import annotations

import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from botocore.exceptions import ClientError

from app.config import (
    ALL_PARAM_NAMES,
    ConfigurationError,
    SSM_PREFIX,
    invalidate_cache,
    load_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ssm_response(present: list[str], missing: list[str] | None = None) -> dict:
    """Build a mock SSM GetParameters response."""
    params = [
        {
            "Name": f"{SSM_PREFIX}/{name}",
            "Value": f"mock-value-{name}",
            "Type": "String",
        }
        for name in present
    ]
    return {
        "Parameters": params,
        "InvalidParameters": [f"{SSM_PREFIX}/{n}" for n in (missing or [])],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSSMLoader:
    def setup_method(self) -> None:
        """Clear cache before each test."""
        invalidate_cache()

    def teardown_method(self) -> None:
        """Clear cache after each test."""
        invalidate_cache()

    # --- Case 1: all params present ---

    def test_all_params_returns_correct_dict(self) -> None:
        mock_client = MagicMock()
        mock_client.get_parameters.return_value = _make_ssm_response(ALL_PARAM_NAMES)

        with patch("boto3.client", return_value=mock_client):
            config = load_config()

        assert set(config.keys()) == set(ALL_PARAM_NAMES)
        for name in ALL_PARAM_NAMES:
            assert config[name] == f"mock-value-{name}"

    # --- Case 2: missing parameter → ConfigurationError naming it ---

    def test_missing_param_raises_config_error(self) -> None:
        present = [n for n in ALL_PARAM_NAMES if n != "guardrail_id"]
        mock_client = MagicMock()
        mock_client.get_parameters.return_value = _make_ssm_response(present)

        # Also ensure env fallback doesn't mask the error
        env_patch = {f"NUTRIGUARD_{n.upper()}": "" for n in ALL_PARAM_NAMES}

        with patch("boto3.client", return_value=mock_client):
            with patch.dict(os.environ, env_patch, clear=False):
                with pytest.raises(ConfigurationError) as exc_info:
                    load_config()

        assert "guardrail_id" in str(exc_info.value).lower() or \
               "NUTRIGUARD_GUARDRAIL_ID" in str(exc_info.value)

    # --- Case 3: cache hit — SSM called only once ---

    def test_cache_hit(self) -> None:
        mock_client = MagicMock()
        mock_client.get_parameters.return_value = _make_ssm_response(ALL_PARAM_NAMES)

        with patch("boto3.client", return_value=mock_client):
            config1 = load_config()
            config2 = load_config()

        # boto3.client called once for the whole process (cached)
        assert config1 == config2
        # SSM get_parameters called only once
        assert mock_client.get_parameters.call_count == 1

    # --- Case 4: invalidate_cache clears cache ---

    def test_invalidate_cache_triggers_reload(self) -> None:
        mock_client = MagicMock()
        mock_client.get_parameters.return_value = _make_ssm_response(ALL_PARAM_NAMES)

        with patch("boto3.client", return_value=mock_client):
            load_config()
            invalidate_cache()
            load_config()

        assert mock_client.get_parameters.call_count == 2

    # --- Case 5: SSM ClientError → env fallback ---

    def test_ssm_client_error_falls_back_to_env(self) -> None:
        mock_client = MagicMock()
        mock_client.get_parameters.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
            "GetParameters",
        )

        env_values = {f"NUTRIGUARD_{n.upper()}": f"env-value-{n}" for n in ALL_PARAM_NAMES}

        with patch("boto3.client", return_value=mock_client):
            with patch.dict(os.environ, env_values):
                config = load_config()

        for name in ALL_PARAM_NAMES:
            assert config[name] == f"env-value-{name}"

    # --- Case 6: both SSM and env fail → ConfigurationError ---

    def test_both_sources_fail_raises_config_error(self) -> None:
        mock_client = MagicMock()
        mock_client.get_parameters.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
            "GetParameters",
        )

        # Clear all NUTRIGUARD_ env vars to force fallback failure
        env_clear = {f"NUTRIGUARD_{n.upper()}": "" for n in ALL_PARAM_NAMES}

        with patch("boto3.client", return_value=mock_client):
            with patch.dict(os.environ, env_clear):
                with pytest.raises(ConfigurationError) as exc_info:
                    load_config()

        assert "cannot load configuration" in str(exc_info.value).lower() or \
               "ssm" in str(exc_info.value).lower()
