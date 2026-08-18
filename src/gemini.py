"""Gemini API client for PR code analysis and review generation."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import httpx
from ssm_secrets import get_gemini_api_key

logger = logging.getLogger()

GEMINI_API_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Pinned id, never a `-latest` alias. Free-tier quota is metered *per model*,
# so the id we send is the quota bucket. `gemini-flash-latest` silently
# re-pointed to gemini-3.6-flash, whose free tier is 20 requests/**day**, and
# every review after the 20th of the day failed the required check outright.
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")

# Tried in order once the primary model's quota is spent. Each id is its own
# free-tier bucket, so exhausting one still leaves a review path open.
FALLBACK_MODELS = [
    m.strip()
    for m in os.environ.get(
        "GEMINI_FALLBACK_MODELS", "gemini-3.5-flash-lite,gemini-3.1-flash-lite"
    ).split(",")
    if m.strip()
]

# Total wall-clock we will spend sleeping between retries. Must stay well
# under the Lambda timeout — see the timeout invariant in CLAUDE.md.
RETRY_BUDGET_SECONDS = float(os.environ.get("GEMINI_RETRY_BUDGET_SECONDS", "45"))
REQUEST_TIMEOUT_SECONDS = 45.0
MAX_ATTEMPTS_PER_MODEL = 4

_DURATION_RE = re.compile(r"^([0-9.]+)s$")


class GeminiQuotaExhausted(RuntimeError):
    """Every candidate model answered 429 RESOURCE_EXHAUSTED.

    Carries `status_description` so the commit status says *why* instead of
    the useless `Review failed: HTTPStatusError`.
    """

    def __init__(self, failures: list[_ModelQuotaExhausted]) -> None:
        self.failures = failures
        models = ", ".join(f.model for f in failures) or "none"
        waits = [f.retry_after for f in failures if f.retry_after]
        hint = f"; retry in ~{int(min(waits))}s" if waits else ""
        self.status_description = f"Gemini quota exhausted ({models}){hint}"
        super().__init__(self.status_description)


class _ModelQuotaExhausted(Exception):
    """One model is out of quota; the caller may try the next one."""

    def __init__(self, model: str, retry_after: float | None, daily: bool) -> None:
        self.model = model
        self.retry_after = retry_after
        self.daily = daily
        super().__init__(f"{model} quota exhausted (daily={daily})")


def _error_details(body: dict) -> list[dict]:
    return body.get("error", {}).get("details") or []


def _retry_delay(body: dict) -> float | None:
    """Google's own RetryInfo hint, in seconds.

    Blind exponential backoff is useless against this API: it answers a
    per-minute 429 with `retryDelay: 32s` while 2s/4s/8s never clears the
    window, so all four attempts burn quota and fail together.
    """
    for detail in _error_details(body):
        if str(detail.get("@type", "")).endswith("RetryInfo"):
            match = _DURATION_RE.match(str(detail.get("retryDelay", "")))
            if match:
                return float(match.group(1))
    return None


def _quota_ids(body: dict) -> list[str]:
    ids = []
    for detail in _error_details(body):
        if str(detail.get("@type", "")).endswith("QuotaFailure"):
            for violation in detail.get("violations") or []:
                ids.append(str(violation.get("quotaId", "")))
    return ids


def _is_daily_quota(body: dict) -> bool:
    """True for a per-day cap, which no amount of waiting inside one Lambda
    invocation will clear — the only useful move is a different model."""
    return any("PerDay" in quota_id for quota_id in _quota_ids(body))


def _json_or_empty(resp: httpx.Response) -> dict:
    try:
        body = resp.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


SYSTEM_PROMPT = """You are Gemini PR Reviewer, an expert AI staff software engineer and code reviewer.
Your mission is to perform a thorough, constructive, and highly actionable code review for a GitHub Pull Request.

Target Audience for Review:
The developer and AI coding assistants (e.g. Cursor, Claude, Antigravity). Your review must provide clear explanations AND structured, copy-pasteable instructions for an AI assistant to apply all recommended changes automatically.

Review Criteria:
1. Correctness & Logic: Check for subtle bugs, race conditions, edge-case failures, unhandled exceptions.
2. Architecture & Design: Clean abstractions, proper error handling, alignment with project patterns.
3. Security & Data Protection: No hardcoded secrets, input sanitization, OWASP top 10 compliance.
4. Performance & Efficiency: Unnecessary DB queries, allocations, blocking I/O on async loops.

Formatting Requirements for Your Response:
Structure your response in Markdown with these exact sections:

### 📌 Executive Summary
A concise 2-3 sentence overview of the pull request changes, overall risk assessment, and key strengths.

### 🔍 Key Findings & Assessment
Categorize findings by severity:
- 🔴 **Critical / Blockers** (Bugs, security risks, breaking changes)
- 🟡 **Improvements & Suggestions** (Refactoring, edge cases, performance)
- 🟢 **Positives** (Well-written code, good patterns)

### 📝 Detailed File-by-File Review
For each modified file where changes are suggested, explain the context, the issue, and show proposed edits with standard diff syntax (`diff`) or code blocks.

### 🤖 AI Assistant Copy-Paste Directive
Include a dedicated section formatted as a blockquote / checklist that a developer can copy-paste directly into Cursor / Claude / Antigravity to automatically execute all approved modifications.
Example format:
```markdown
<PR_REVIEW_ACTIONS>
- [ ] Task 1: Fix edge case in `path/to/file.py` line XX. Replace function Y with Z.
- [ ] Task 2: Refactor DB query in `path/to/db.py` to use parameterized queries.
</PR_REVIEW_ACTIONS>
```
"""


class GeminiClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        fallback_models: list[str] | None = None,
    ) -> None:
        self.api_key = api_key or get_gemini_api_key()
        self.model = model
        self.fallback_models = FALLBACK_MODELS if fallback_models is None else fallback_models

    async def generate_review(
        self,
        pr_title: str,
        pr_body: str,
        files_summary: str,
        diff_content: str,
    ) -> str:
        """Call Gemini API to generate a code review for a PR diff."""
        # Truncate diff if extremely large to fit token context comfortably
        max_diff_len = 80_000
        truncated_diff = diff_content[:max_diff_len]
        if len(diff_content) > max_diff_len:
            truncated_diff += f"\n\n... [Diff truncated at {max_diff_len} chars out of {len(diff_content)} total chars]"

        user_content = f"""
## Pull Request Details
**Title:** {pr_title}
**Description:**
{pr_body or 'No description provided.'}

## Changed Files Summary
{files_summary}

## Unified Diff
```diff
{truncated_diff}
```
"""

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": SYSTEM_PROMPT},
                        {"text": user_content},
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 4096,
            },
        }

        candidates = [self.model] + [m for m in self.fallback_models if m != self.model]
        exhausted: list[_ModelQuotaExhausted] = []

        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            deadline = asyncio.get_running_loop().time() + RETRY_BUDGET_SECONDS
            for model in candidates:
                logger.info("Calling Gemini API (%s) for PR analysis...", model)
                try:
                    return await self._generate(client, model, payload, deadline)
                except _ModelQuotaExhausted as exc:
                    exhausted.append(exc)
                    logger.warning(
                        "Gemini quota exhausted for %s (daily=%s, retry_after=%ss)%s",
                        exc.model,
                        exc.daily,
                        exc.retry_after,
                        "; falling back to next model" if model != candidates[-1] else "",
                    )

        raise GeminiQuotaExhausted(exhausted)

    async def _generate(
        self,
        client: httpx.AsyncClient,
        model: str,
        payload: dict,
        deadline: float,
    ) -> str:
        """One model's request + retry loop. Raises _ModelQuotaExhausted on 429."""
        # The key travels in a header, never the URL: httpx logs every request
        # URL at INFO, so a ?key= query string ends up in CloudWatch verbatim.
        url = GEMINI_API_ENDPOINT.format(model=model)

        for attempt in range(1, MAX_ATTEMPTS_PER_MODEL + 1):
            resp = await client.post(
                url, json=payload, headers={"x-goog-api-key": self.api_key}
            )
            if resp.status_code == 200:
                return _extract_review(resp.json())

            # 429/5xx are routine for generativelanguage.googleapis.com under
            # load (observed: 503 UNAVAILABLE failing a review outright, which
            # left a required gemini-pr-review check stuck red on a transient).
            # Anything else 4xx is a real request problem — no retry.
            body = _json_or_empty(resp)
            retryable = resp.status_code == 429 or resp.status_code >= 500
            hinted = _retry_delay(body)
            daily = resp.status_code == 429 and _is_daily_quota(body)
            delay = hinted if hinted is not None else 2 ** attempt
            remaining = deadline - asyncio.get_running_loop().time()
            # A per-day cap cannot clear inside this invocation, and a wait we
            # cannot afford is not a wait — either way, stop burning quota on
            # this model and let the caller try the next one.
            out_of_road = daily or delay > remaining or attempt == MAX_ATTEMPTS_PER_MODEL

            logger.error(
                "Gemini API error %d on %s (attempt %d/%d%s): %s",
                resp.status_code,
                model,
                attempt,
                MAX_ATTEMPTS_PER_MODEL,
                ", giving up" if out_of_road or not retryable else f", retrying in {delay:.0f}s",
                str(body.get("error", {}).get("message", resp.text))[:300],
            )

            if resp.status_code == 429 and (out_of_road or not retryable):
                raise _ModelQuotaExhausted(model, hinted, daily)
            if not retryable or out_of_road:
                resp.raise_for_status()
            await asyncio.sleep(delay)

        raise RuntimeError("unreachable: retry loop exited without a verdict")


def _extract_review(data: dict) -> str:
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        logger.error("Failed to parse Gemini response payload: %s", data)
        raise RuntimeError("Invalid response structure from Gemini API") from exc
