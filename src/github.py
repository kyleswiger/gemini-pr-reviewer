"""GitHub REST API client for fetching PR diffs and posting reviews."""
from __future__ import annotations

import logging
import httpx
from ssm_secrets import get_github_token

logger = logging.getLogger()
GITHUB_API_BASE = "https://api.github.com"

# The status context branch rulesets require. Changing this string orphans the
# required check in every ruleset that names it.
COMMIT_STATUS_CONTEXT = "gemini-pr-review"


class GitHubClient:
    def __init__(self, token: str | None = None) -> None:
        self.token = token or get_github_token()
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "gemini-pr-reviewer/1.0",
        }

    async def get_pr_diff(self, repo: str, pr_number: int) -> str:
        """Fetch the unified diff of a pull request."""
        url = f"{GITHUB_API_BASE}/repos/{repo}/pulls/{pr_number}"
        diff_headers = {**self.headers, "Accept": "application/vnd.github.v3.diff"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=diff_headers)
            resp.raise_for_status()
            return resp.text

    async def get_pr_files(self, repo: str, pr_number: int) -> list[dict]:
        """Fetch changed files list for a pull request."""
        url = f"{GITHUB_API_BASE}/repos/{repo}/pulls/{pr_number}/files"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=self.headers)
            resp.raise_for_status()
            return resp.json()

    async def post_commit_status(
        self,
        repo: str,
        sha: str,
        state: str,
        description: str,
        context: str = COMMIT_STATUS_CONTEXT,
        target_url: str | None = None,
    ) -> dict | None:
        """Set a commit status so branch rulesets can require the review.

        Failures here are logged and swallowed: a status we cannot write must
        never abort the review itself. The consequence is a check stuck on
        `pending`, which fails closed against the ruleset.
        """
        url = f"{GITHUB_API_BASE}/repos/{repo}/statuses/{sha}"
        payload = {
            "state": state,
            "context": context,
            # GitHub truncates past 140 chars and rejects nothing, so trim here.
            "description": description[:140],
        }
        if target_url:
            payload["target_url"] = target_url

        logger.info("Setting commit status %s=%s on %s@%s", context, state, repo, sha)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=self.headers, json=payload)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError:
            logger.exception(
                "Failed to set commit status %s=%s on %s@%s", context, state, repo, sha
            )
            return None

    async def post_pr_review(
        self,
        repo: str,
        pr_number: int,
        body: str,
        commit_sha: str | None = None,
        event: str = "COMMENT",
    ) -> dict:
        """Post a pull request review comment."""
        url = f"{GITHUB_API_BASE}/repos/{repo}/pulls/{pr_number}/reviews"
        payload = {
            "body": body,
            "event": event,
        }
        if commit_sha:
            payload["commit_id"] = commit_sha

        logger.info("Posting PR review to %s #%d (event=%s)", repo, pr_number, event)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=self.headers, json=payload)
            resp.raise_for_status()
            return resp.json()
