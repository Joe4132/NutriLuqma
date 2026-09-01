"""
SSM configuration loader — app/config.py

Rules (from PERSON1_GATE_A_PLAN.md §P1-03):
- All resource identifiers come from SSM. Nothing is hardcoded.
- Region is fixed to us-west-2.
- Missing parameter → clear startup error naming the parameter, never a silent default.
- Results are cached after the first load; cache is per-process.
- If IAM blocks SSM writes, falls back to agentcore/.env.local behind the
  SAME interface — so callers are never aware of the source.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REGION = "us-west-2"
SSM_PREFIX = "/nutriguard/gate-a"

# Parameter names (relative to prefix)
PARAM_TABLE_NAME = "table_name"
PARAM_BUCKET_NAME = "bucket_name"
PARAM_KB_ID = "kb_id"
PARAM_GUARDRAIL_ID = "guardrail_id"
PARAM_GUARDRAIL_VERSION = "guardrail_version"

ALL_PARAM_NAMES = [
    PARAM_TABLE_NAME,
    PARAM_BUCKET_NAME,
    PARAM_KB_ID,
    PARAM_GUARDRAIL_ID,
    PARAM_GUARDRAIL_VERSION,
]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ConfigurationError(RuntimeError):
    """Raised when a required configuration parameter cannot be found."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _env_fallback_key(name: str) -> str:
    """Convert SSM parameter name to env-var style for .env.local fallback."""
    return f"NUTRIGUARD_{name.upper()}"


def _load_from_ssm(names: list[str]) -> dict[str, str]:
    """
    Fetch parameters from SSM under SSM_PREFIX.
    Raises ConfigurationError for any missing parameter.
    """
    ssm = boto3.client("ssm", region_name=REGION)
    full_names = [f"{SSM_PREFIX}/{n}" for n in names]

    try:
        response = ssm.get_parameters(Names=full_names, WithDecryption=True)
    except NoCredentialsError as exc:
        raise ConfigurationError(
            "AWS credentials not configured. Run `aws configure` first."
        ) from exc
    except ClientError as exc:
        raise ConfigurationError(
            f"SSM GetParameters failed: {exc}"
        ) from exc

    found: dict[str, str] = {}
    for param in response.get("Parameters", []):
        short_name = param["Name"].replace(f"{SSM_PREFIX}/", "")
        found[short_name] = param["Value"]

    missing = [n for n in names if n not in found]
    if missing:
        missing_full = [f"{SSM_PREFIX}/{n}" for n in missing]
        raise ConfigurationError(
            f"Required SSM parameters not found: {missing_full}. "
            "Create them with: "
            "aws ssm put-parameter --name <name> --value <value> "
            "--type String --overwrite --region us-west-2"
        )

    return found


def _load_from_env(names: list[str]) -> dict[str, str]:
    """
    Fallback: load from environment variables (populated from agentcore/.env.local).
    Raises ConfigurationError for any missing variable.
    """
    result: dict[str, str] = {}
    missing: list[str] = []
    for name in names:
        env_key = _env_fallback_key(name)
        value = os.environ.get(env_key)
        if value:
            result[name] = value
        else:
            missing.append(env_key)
    if missing:
        raise ConfigurationError(
            f"SSM unavailable and env fallback missing: {missing}. "
            "Populate agentcore/.env.local or configure AWS credentials."
        )
    return result


# ---------------------------------------------------------------------------
# Public API — cached loader
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_config() -> dict[str, str]:
    """
    Load all Gate A configuration parameters.

    Tries SSM first. Falls back to environment variables if SSM is unavailable
    (e.g. local dev without IAM). Either way, all parameters must be present.

    Returns:
        dict mapping short parameter names to their values.
        Keys: table_name, bucket_name, kb_id, guardrail_id, guardrail_version.

    Raises:
        ConfigurationError: if any required parameter is missing from both sources.
    """
    try:
        config = _load_from_ssm(ALL_PARAM_NAMES)
        return config
    except ConfigurationError as ssm_err:
        # Try env fallback before giving up
        try:
            config = _load_from_env(ALL_PARAM_NAMES)
            # Log the deviation so it's visible in startup output
            print(
                f"[config] WARNING: SSM unavailable ({ssm_err}). "
                "Using environment variable fallback from agentcore/.env.local."
            )
            return config
        except ConfigurationError as env_err:
            raise ConfigurationError(
                f"Cannot load configuration from SSM or env fallback.\n"
                f"SSM error: {ssm_err}\n"
                f"Env error: {env_err}"
            ) from env_err


def get(key: str) -> str:
    """
    Convenience accessor. Raises ConfigurationError if key is missing.

    Usage:
        table = config.get("table_name")
        guardrail_id = config.get("guardrail_id")
    """
    cfg = load_config()
    if key not in cfg:
        raise ConfigurationError(
            f"Configuration key {key!r} not in loaded config. "
            f"Available keys: {list(cfg.keys())}"
        )
    return cfg[key]


def invalidate_cache() -> None:
    """Clear the cached config (used in tests to reset between test cases)."""
    load_config.cache_clear()
