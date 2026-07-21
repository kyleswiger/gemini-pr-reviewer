"""SSM Parameter Store secret manager with in-memory caching."""
from __future__ import annotations

import logging
import os
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()

SSM_PARAMETER_PREFIX = os.environ.get("SSM_PARAMETER_PREFIX", "/gemini-pr-reviewer")
WEBHOOK_SECRET_PARAM = f"{SSM_PARAMETER_PREFIX}/webhook_secret"
GITHUB_TOKEN_PARAM = f"{SSM_PARAMETER_PREFIX}/github_token"
GEMINI_API_KEY_PARAM = f"{SSM_PARAMETER_PREFIX}/gemini_api_key"

_ssm_client = None
_secret_cache: dict[str, str] = {}


def _get_ssm():
    global _ssm_client
    if _ssm_client is None:
        _ssm_client = boto3.client("ssm")
    return _ssm_client


def get_secret(name: str, fallback_env_var: str | None = None) -> str:
    """Fetch a SecureString parameter from SSM, cached per execution environment.
    
    If parameter is missing or fails to load, attempts fallback_env_var if provided.
    """
    if name in _secret_cache:
        return _secret_cache[name]

    try:
        response = _get_ssm().get_parameter(Name=name, WithDecryption=True)
        val = response["Parameter"]["Value"]
        _secret_cache[name] = val
        return val
    except ClientError as exc:
        if fallback_env_var and os.environ.get(fallback_env_var):
            logger.warning("SSM parameter %s failed; using env var %s", name, fallback_env_var)
            val = os.environ[fallback_env_var]
            _secret_cache[name] = val
            return val
        logger.exception("Failed to fetch SSM parameter %s", name)
        raise RuntimeError(f"unable to load secret {name}") from exc


def get_webhook_secret() -> str:
    return get_secret(WEBHOOK_SECRET_PARAM, fallback_env_var="WEBHOOK_SECRET")


def get_github_token() -> str:
    return get_secret(GITHUB_TOKEN_PARAM, fallback_env_var="GITHUB_TOKEN")


def get_gemini_api_key() -> str:
    return get_secret(GEMINI_API_KEY_PARAM, fallback_env_var="GEMINI_API_KEY")
