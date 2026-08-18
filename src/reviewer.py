"""Orchestrator for the Gemini PR review pipeline."""
from __future__ import annotations

import logging
from github import GitHubClient
from gemini import GeminiClient, GeminiQuotaExhausted

logger = logging.getLogger()


async def run_pr_review_pipeline(payload: dict) -> dict:
    """Process a pull_request webhook payload and post review to GitHub.

    Wraps the pipeline so the `gemini-pr-review` commit status always resolves.
    The status reports whether a review *completed*, not whether Gemini liked
    the change — the gate is "an agentic review ran against this commit".
    """
    repo = payload.get("repository", {}).get("full_name")
    sha = payload.get("pull_request", {}).get("head", {}).get("sha")

    try:
        result = await _run_pr_review_pipeline(payload)
    except GeminiQuotaExhausted as exc:
        # Deliberately NOT re-raised. Lambda retries an async invocation twice,
        # and each retry re-runs every candidate model — against a per-day cap
        # that is 6 more wasted requests and the same red status at the end.
        logger.error("PR review out of Gemini quota for %s@%s: %s", repo, sha, exc)
        await _report_status(repo, sha, "error", exc.status_description)
        return {"success": False, "reason": "quota_exhausted"}
    except Exception as exc:
        logger.exception("PR review pipeline failed for %s@%s", repo, sha)
        await _report_status(repo, sha, "error", f"Review failed: {type(exc).__name__}")
        raise

    if result.get("success"):
        await _report_status(repo, sha, "success", _describe(result))
    else:
        await _report_status(
            repo, sha, "error", f"Review did not run: {result.get('reason', 'unknown')}"
        )
    return result


def _describe(result: dict) -> str:
    if result.get("reason") == "empty_diff":
        return "No reviewable changes in this pull request"
    return "Gemini review posted"


async def _report_status(repo: str | None, sha: str | None, state: str, description: str) -> None:
    if not repo or not sha:
        logger.warning("no repo/sha available; skipping %s status", state)
        return
    try:
        await GitHubClient().post_commit_status(
            repo=repo, sha=sha, state=state, description=description
        )
    except Exception:
        logger.exception("Failed to report %s status for %s@%s", state, repo, sha)


async def _run_pr_review_pipeline(payload: dict) -> dict:
    pr_data = payload.get("pull_request", {})
    repo_data = payload.get("repository", {})

    repo_full_name = repo_data.get("full_name")
    pr_number = pr_data.get("number")
    pr_title = pr_data.get("title", "Untitled PR")
    pr_body = pr_data.get("body", "")
    head_sha = pr_data.get("head", {}).get("sha")

    if not repo_full_name or not pr_number:
        logger.error("Missing repository full_name or PR number in payload")
        return {"success": False, "reason": "invalid_payload"}

    logger.info(
        "Starting PR review pipeline for %s #%d (head_sha=%s)",
        repo_full_name,
        pr_number,
        head_sha,
    )

    gh_client = GitHubClient()
    gemini_client = GeminiClient()

    # Step 1: Fetch PR diff & file list
    diff_content = await gh_client.get_pr_diff(repo_full_name, pr_number)
    files = await gh_client.get_pr_files(repo_full_name, pr_number)

    if not diff_content.strip():
        logger.info("PR %s #%d has empty diff. Skipping review.", repo_full_name, pr_number)
        return {"success": True, "reason": "empty_diff"}

    files_summary_lines = []
    for f in files:
        filename = f.get("filename", "unknown")
        status = f.get("status", "modified")
        additions = f.get("additions", 0)
        deletions = f.get("deletions", 0)
        files_summary_lines.append(f"- `{filename}` ({status}): +{additions} / -{deletions}")

    files_summary = "\n".join(files_summary_lines)

    # Step 2: Generate review with Gemini
    review_markdown = await gemini_client.generate_review(
        pr_title=pr_title,
        pr_body=pr_body,
        files_summary=files_summary,
        diff_content=diff_content,
    )

    # Step 3: Post review comment to GitHub PR
    header = (
        "## 🤖 Gemini Automated Code Review\n\n"
        "> *Reviewed automatically by [Gemini PR Reviewer](https://github.com/kyleswiger/gemini-pr-reviewer)*\n\n"
    )
    full_body = header + review_markdown

    result = await gh_client.post_pr_review(
        repo=repo_full_name,
        pr_number=pr_number,
        body=full_body,
        commit_sha=head_sha,
        event="COMMENT",
    )

    logger.info("Successfully posted review for %s #%d!", repo_full_name, pr_number)
    return {"success": True, "review_id": result.get("id")}
