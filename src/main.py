"""GitHub webhook receiver for the Gemini PR Reviewer."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os

import boto3
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from mangum import Mangum

from ssm_secrets import get_webhook_secret
from reviewer import run_pr_review_pipeline

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

_lambda_client = boto3.client("lambda")


def verify_signature(payload: bytes, signature_header: str | None, secret: str) -> bool:
    """Constant-time verification of GitHub's X-Hub-Signature-256 header."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    provided = signature_header.split("=", 1)[1]
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)


app = FastAPI(title="Gemini PR Reviewer", version="0.2.0")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request) -> JSONResponse:
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    event = request.headers.get("X-GitHub-Event", "unknown")
    delivery = request.headers.get("X-GitHub-Delivery", "unknown")

    # If payload is passed via async Lambda invocation
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError:
        logger.warning("malformed json delivery=%s", delivery)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid json"
        )

    # Check if this is an internal async invocation
    if payload.get("is_async_exec") is True:
        logger.info("Executing async PR review pipeline delivery=%s", delivery)
        result = await run_pr_review_pipeline(payload)
        return JSONResponse(status_code=200, content=result)

    # Validate webhook secret from SSM
    try:
        secret = get_webhook_secret()
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

    action = payload.get("action", "n/a")
    logger.info(
        "received github event=%s action=%s delivery=%s", event, action, delivery
    )

    # Only process pull_request events for relevant actions
    if event == "pull_request" and action in ("opened", "synchronize", "reopened", "edited"):
        function_name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
        if function_name:
            # Asynchronously invoke self to decouple review pipeline from GitHub's 10s timeout
            payload["is_async_exec"] = True
            logger.info("Queuing async Lambda invocation function=%s delivery=%s", function_name, delivery)
            try:
                _lambda_client.invoke(
                    FunctionName=function_name,
                    InvocationType="Event",  # Async execution
                    Payload=json.dumps(payload),
                )
                return JSONResponse(
                    status_code=200,
                    content={"received": True, "status": "queued", "event": event, "action": action},
                )
            except Exception as exc:
                logger.exception("Failed to trigger async Lambda invocation")
                # Fallback to in-flight processing if self-invoke fails
                result = await run_pr_review_pipeline(payload)
                return JSONResponse(status_code=200, content=result)

        # Local execution / non-Lambda fallback
        result = await run_pr_review_pipeline(payload)
        return JSONResponse(status_code=200, content=result)

    return JSONResponse(
        status_code=200,
        content={"received": True, "status": "ignored", "event": event, "action": action},
    )


handler = Mangum(app, lifespan="off")
