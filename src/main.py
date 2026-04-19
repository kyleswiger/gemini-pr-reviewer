"""GitHub webhook receiver for the Gemini PR Reviewer.

Phase 1 scope: acknowledge GitHub webhook deliveries within the 3-second
window after verifying the HMAC-SHA256 signature with a secret loaded
from AWS SSM Parameter Store. Downstream review orchestration is added
in Phase 2.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os

import boto3
from botocore.exceptions import ClientError
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from mangum import Mangum

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

SSM_PARAMETER_PREFIX = os.environ.get("SSM_PARAMETER_PREFIX", "/gemini-pr-reviewer")
WEBHOOK_SECRET_PARAMETER = f"{SSM_PARAMETER_PREFIX}/webhook_secret"

_ssm_client = boto3.client("ssm")
_secret_cache: dict[str, str] = {}


def get_secret(name: str) -> str:
    """Fetch a SecureString parameter from SSM, cached per execution env."""
    cached = _secret_cache.get(name)
    if cached is not None:
        return cached
    try:
        response = _ssm_client.get_parameter(Name=name, WithDecryption=True)
    except ClientError as exc:
        logger.exception("Failed to fetch SSM parameter %s", name)
        raise RuntimeError(f"unable to load secret {name}") from exc
    value = response["Parameter"]["Value"]
    _secret_cache[name] = value
    return value


def verify_signature(payload: bytes, signature_header: str | None, secret: str) -> bool:
    """Constant-time verification of GitHub's X-Hub-Signature-256 header."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    provided = signature_header.split("=", 1)[1]
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)


app = FastAPI(title="Gemini PR Reviewer", version="0.1.0")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request) -> JSONResponse:
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    event = request.headers.get("X-GitHub-Event", "unknown")
    delivery = request.headers.get("X-GitHub-Delivery", "unknown")

    try:
        secret = get_secret(WEBHOOK_SECRET_PARAMETER)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="webhook secret unavailable",
        )

    if not verify_signature(body, signature, secret):
        logger.warning("invalid signature event=%s delivery=%s", event, delivery)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature"
        )

    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError:
        logger.warning("malformed json delivery=%s", delivery)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid json"
        )

    action = payload.get("action", "n/a")
    logger.info(
        "received github event=%s action=%s delivery=%s", event, action, delivery
    )

    # Phase 2 hands off here to the review pipeline (likely async via SQS
    # or a self-invoke Lambda) so we stay under GitHub's 10s webhook timeout.
    return JSONResponse(status_code=200, content={"received": True, "event": event})


handler = Mangum(app, lifespan="off")
