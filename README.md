# Gemini PR Reviewer

A blazing-fast, secure, and cost-effective GitHub PR Review automation tool powered by Google's Gemini API and AWS Serverless infrastructure.

## Why this tool?
Current solutions like Gemini Code Assist can be slow or rely on older model versions. This tool is built to use your own Google AI Pro API grants to access the latest models (like Gemini 1.5 Pro). Furthermore, it is designed with a **bi-directional AI workflow** in mind: it structures its feedback so that local AI assistants like Cursor and Claude can easily ingest the review comments and automatically apply the suggested fixes.

## Features
*   **Latest Gemini Models:** Bring your own API key to utilize the bleeding-edge Google AI models.
*   **Cursor/Claude Optimized:** Reviews are formatted specifically to be easily parsed and applied by your local AI IDE.
*   **Serverless & Cheap:** Runs on AWS Lambda. You only pay for the milliseconds it takes to run, leveraging AWS's generous free tier. No persistent servers required.
*   **Secure:** Built for public release. Secrets are fetched securely at runtime via AWS SSM or Secrets Manager. Webhook payloads are strictly verified.

## Architecture (Phase 1)

```
GitHub ──webhook──▶ Lambda Function URL ──▶ FastAPI (Mangum) ──▶ SSM Parameter Store
                                             │
                                             └─▶ CloudWatch Logs
```

- **Compute:** single AWS Lambda (Python 3.12) fronted by a public Function URL — no API Gateway, no VPC, sub-100ms cold starts on warm invocations.
- **Auth:** Function URL is unauthenticated at the edge; GitHub's `X-Hub-Signature-256` HMAC is verified in-app (constant-time compare) against a secret pulled from SSM.
- **Secrets:** all secrets live in SSM SecureString parameters under `/gemini-pr-reviewer/*`. Nothing sensitive is stored in this repo or in Terraform state beyond the ARN.
- **Observability:** structured logs → CloudWatch (14-day retention by default).

## Repository Layout

```
src/              Lambda source (FastAPI + Mangum)
  main.py         POST /webhook handler + signature verification
  requirements.txt
terraform/        IaC for the Lambda, IAM, Function URL, log group
  main.tf
  variables.tf
  lambda.tf
  outputs.tf
```

## Prerequisites

- Terraform `>= 1.5`
- AWS credentials with permission to create IAM roles, Lambda functions, and CloudWatch log groups (e.g. `export AWS_PROFILE=...`)
- Python 3.12 + `pip` on the PATH (Terraform shells out to `pip` to build the deployment package)
- A GitHub App or repository webhook secret (a long random string — you'll create it below)

## Deployment

### 1. Create the SSM secret

Create the webhook secret as a `SecureString` under the project prefix. This is the one thing you must do by hand — it intentionally stays out of Terraform so the secret never lands in state.

```bash
aws ssm put-parameter \
  --name "/gemini-pr-reviewer/webhook_secret" \
  --type SecureString \
  --value "$(openssl rand -hex 32)" \
  --region us-east-1
```

Keep the generated value — you'll paste the same string into GitHub when registering the webhook.

### 2. Deploy the Lambda

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

On apply, Terraform will:
1. `pip install` the Lambda dependencies into `terraform/.build/package/` (Linux wheels pinned to the Lambda architecture).
2. Zip the package + `src/*.py` into `terraform/.build/lambda.zip`.
3. Create the IAM role, scoped SSM read policy, CloudWatch log group, Lambda function, and public Function URL.

The outputs include `webhook_url`. The GitHub webhook target is that URL with `webhook` appended:

```
https://<id>.lambda-url.<region>.on.aws/webhook
```

### 3. Register the webhook in GitHub

In the GitHub App (or repo) settings:

- **Payload URL:** `<webhook_url>webhook`
- **Content type:** `application/json`
- **Secret:** the value you put into SSM above
- **Events:** at minimum, `Pull requests`

### 4. Verify

Send a test delivery from GitHub and tail the logs:

```bash
aws logs tail /aws/lambda/gemini-pr-reviewer --follow --region us-east-1
```

Expected: `received github event=pull_request action=opened delivery=<uuid>` and GitHub showing a 200 response within a few hundred ms.

## Configuration

All defaults live in `terraform/variables.tf`. Override via `-var` or a `terraform.tfvars` file (git-ignored). Common overrides:

| Variable | Default | Notes |
|---|---|---|
| `aws_region` | `us-east-1` | Where everything deploys. |
| `lambda_architecture` | `x86_64` | Set to `arm64` for cheaper Graviton runs. |
| `lambda_memory_mb` | `512` | More memory also means more CPU — bump if cold starts lag. |
| `log_retention_days` | `14` | CloudWatch retention. |

## Roadmap

See [`MASTER_PLAN.md`](./MASTER_PLAN.md). Phase 2 wires in the GitHub App credentials (installation tokens), fetches PR diffs, and hands them to Gemini.
