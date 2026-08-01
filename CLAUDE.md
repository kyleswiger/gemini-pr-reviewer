# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A GitHub PR review bot: a single AWS Lambda receives `pull_request` webhooks, pulls the PR diff, asks the Gemini API for a review, and posts it back as a PR review comment plus a `gemini-pr-review` commit status. Reviews are deliberately formatted for downstream AI assistants (the `<PR_REVIEW_ACTIONS>` checklist block in `src/gemini.py`'s `SYSTEM_PROMPT`).

Phase roadmap lives in `MASTER_PLAN.md`; product intent in `REQUIREMENTS.md`. Phases 1–3 are implemented; Phase 4 (docs polish, public release) is partially done — CI exists, but as Claude-based review rather than lint/type-check.

## Commands

Deployment *is* the build — Terraform hashes `src/**/*.{py,txt}` (`local.src_hash` in `terraform/main.tf`) and re-runs `pip install` + zip whenever source changes. There is no separate build step.

```bash
cd terraform && terraform init && terraform apply   # build + deploy
terraform fmt && terraform validate
aws logs tail /aws/lambda/gemini-pr-reviewer --follow --region us-east-1
```

Secrets are created by hand as SSM `SecureString` parameters under `/gemini-pr-reviewer/` — Terraform never touches their values, only grants read access:

```bash
aws ssm put-parameter --name "/gemini-pr-reviewer/webhook_secret" --type SecureString --value "$(openssl rand -hex 32)" --region us-east-1
# also required: /gemini-pr-reviewer/github_token, /gemini-pr-reviewer/gemini_api_key
```

There is no test suite and no linter. CI (`.github/workflows/`) is two `anthropics/claude-code-action` jobs — an automatic PR review and an `@claude` mention handler — not build/lint/test gates, so nothing verifies these sources before deploy. `.venv/` is a local sandbox for importing/poking at `src/` — note it runs Python 3.14 while the Lambda package is built for **3.12** (`--python-version 3.12` in `terraform/lambda.tf`), so it is not a faithful runtime.

For local runs, every secret getter in `src/ssm_secrets.py` falls back to an env var when the SSM read raises `ClientError`: `WEBHOOK_SECRET`, `GITHUB_TOKEN`, `GEMINI_API_KEY`.

## Architecture

```
GitHub ─webhook─▶ Lambda Function URL ─▶ Mangum ─▶ FastAPI /webhook (main.py)
                                                     │  HMAC verify, set pending status
                                                     └─ self-invoke (InvocationType=Event)
                                                          └▶ reviewer.py ─▶ github.py + gemini.py
```

- `src/main.py` — webhook entry. Verifies `X-Hub-Signature-256`, sets the commit status to `pending`, then asynchronously self-invokes the same Lambda so GitHub gets a 200 well inside its timeout. `handler = Mangum(app)` is the Lambda entrypoint (`main.handler`).
- `src/reviewer.py` — pipeline orchestration and the *only* place that guarantees the commit status resolves. `run_pr_review_pipeline` wraps `_run_pr_review_pipeline` so every exit path writes `success`/`error`.
- `src/github.py` — REST client (PAT/token bearer auth, not GitHub App JWT yet). Diff fetch, files list, review post, commit status.
- `src/gemini.py` — direct HTTP call to `generativelanguage.googleapis.com` (no SDK). System prompt + diff truncation at 80k chars live here.
- `src/ssm_secrets.py` — SSM reads cached per execution environment in a module-level dict; cache survives warm invocations, so a rotated secret needs a cold start.
- `terraform/` — one Lambda, one public Function URL (`authorization_type = "NONE"`), IAM role with scoped SSM read + KMS decrypt-via-SSM + self-invoke, explicit log group.

### Invariants worth knowing

- **The Function URL is unauthenticated at the edge.** All auth is the constant-time HMAC compare in `verify_signature`. Any change that lets a request reach the pipeline before that check is a security regression.
- **`COMMIT_STATUS_CONTEXT = "gemini-pr-review"`** (`src/github.py`) is the string branch rulesets reference. Renaming it orphans the required check everywhere it's configured.
- **Status writes fail open, the gate fails closed.** `post_commit_status` swallows its own errors so a status write never aborts a review; the consequence is a check stuck on `pending`, which blocks the merge.
- Lambda timeout is 60s and Gemini's client timeout is 45s — both must be raised together if larger diffs need more headroom.

### Known broken: the async self-invoke path

`main.py` self-invokes with `Payload=json.dumps(payload)` — the *parsed GitHub payload*, not a Lambda HTTP event. Mangum cannot infer a handler for that shape and raises `RuntimeError: The adapter was unable to infer a handler to use for the event` before `is_async_exec` is ever read, so the review never runs and the commit status stays `pending`. (Verified locally against the installed Mangum.) The `is_async_exec` branch inside the FastAPI route is unreachable as written; fixing it means either bypassing Mangum for non-HTTP events in a wrapper handler, or synthesizing an API Gateway v2 event for the self-invoke.
