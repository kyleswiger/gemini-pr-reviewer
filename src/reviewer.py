"""Orchestrator for the Gemini PR review pipeline."""
from __future__ import annotations

import logging
from github import GitHubClient
from gemini import GeminiClient

logger = logging.getLogger()


async def run_pr_review_pipeline(payload: dict) -> dict:
    """Process a pull_request webhook payload and post review to GitHub."""
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
