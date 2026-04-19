# Master Plan: Gemini PR Reviewer

## Phase 1: Foundation & Boilerplate
*   Initialize the repository with a clear open-source structure.
*   Define the core serverless architecture using Terraform (AWS Lambda + API Gateway/Function URL).
*   Set up a Python backend (e.g., using FastAPI and Mangum for seamless Lambda integration) or Go backend.
*   Implement secure secret fetching from AWS SSM Parameter Store/Secrets Manager.
*   Implement GitHub Webhook signature validation to ensure the tool is secure from the ground up.

## Phase 2: GitHub & Gemini Integration
*   Implement the GitHub API client to authenticate as a GitHub App installation (using JWT and Installation Access Tokens).
*   Add logic to fetch the PR diff or specific file contents when a `pull_request` event is received.
*   Integrate the Google GenAI SDK and configure it to use the Gemini 1.5 Pro model.
*   Draft a highly specialized system prompt for Gemini that instructs it to format its output specifically for consumption by Cursor/Claude (e.g., clear file paths, unified diffs, and actionable checklist items).

## Phase 3: The Bi-directional Feedback Loop
*   Parse Gemini's structured response.
*   Map the feedback to GitHub's Review API, posting both a high-level summary comment and inline code comments.
*   Ensure the summary comment includes a "Copy-Paste" section that the user can feed directly back into Cursor to automatically apply all approved suggestions.

## Phase 4: Deployment & Open Source Release
*   Finalize Terraform scripts for easy 1-click deployment to any AWS account.
*   Write comprehensive documentation (`README.md`, `DEPLOYMENT.md`) explaining how to set up the GitHub App, configure AWS, and add the Gemini API key.
*   Add GitHub Actions for CI (linting, type-checking) to maintain code quality in the public repository.
