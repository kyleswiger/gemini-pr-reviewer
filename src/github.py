"""GitHub REST API client for fetching PR diffs and posting reviews."""
from __future__ import annotations

import logging
import httpx
from ssm_secrets import get_github_token

logger = logging.getLogger()
GITHUB_API_BASE = "https://api.github.com"


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
