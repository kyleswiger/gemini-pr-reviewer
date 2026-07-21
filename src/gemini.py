"""Gemini API client for PR code analysis and review generation."""
from __future__ import annotations

import logging
import httpx
from ssm_secrets import get_gemini_api_key

logger = logging.getLogger()

GEMINI_API_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-flash-latest"


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
    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL) -> None:
        self.api_key = api_key or get_gemini_api_key()
        self.model = model

    async def generate_review(
        self,
        pr_title: str,
        pr_body: str,
        files_summary: str,
        diff_content: str,
    ) -> str:
        """Call Gemini API to generate a code review for a PR diff."""
        url = GEMINI_API_ENDPOINT.format(model=self.model) + f"?key={self.api_key}"

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

        logger.info("Calling Gemini API (%s) for PR analysis...", self.model)
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                logger.error("Gemini API error %d: %s", resp.status_code, resp.text)
                resp.raise_for_status()

            data = resp.json()
            try:
                review_text = data["candidates"][0]["content"]["parts"][0]["text"]
                return review_text
            except (KeyError, IndexError) as exc:
                logger.error("Failed to parse Gemini response payload: %s", data)
                raise RuntimeError("Invalid response structure from Gemini API") from exc
