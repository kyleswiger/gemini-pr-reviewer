# Requirements: Gemini PR Reviewer

## 1. Overview
A serverless, robust, and lightning-fast automated PR review tool leveraging the latest Google Gemini API. Designed to seamlessly integrate with GitHub workflows (specifically targeting the `kyleswiger` account/org) and provide actionable, structured feedback that can be easily parsed and applied by AI coding assistants like Cursor and Claude.

## 2. Core Capabilities
*   **Google AI Integration:** Utilizes the Google GenAI SDK to access the latest Gemini models (e.g., Gemini 1.5 Pro) using existing API usage grants.
*   **GitHub Integration:** Operates as a GitHub App or Webhook receiver, listening for `pull_request` (opened, synchronize) events on configured repositories.
*   **Actionable Feedback Loop:** Outputs code reviews in a standardized format (e.g., Markdown checklists, inline code blocks with suggested replacements) so that tools like Cursor can immediately read the PR comments and apply the suggested fixes, enabling a continuous bi-directional AI workflow.
*   **Cloud-Native & Fast:** Deployed as an AWS Lambda function triggered by API Gateway or Function URLs. This ensures near-zero idle costs, infinite scalability, and blazing-fast execution speeds without impacting existing CodeBuild or hosting costs.
*   **Secure by Design:** The repository will be public-facing. No hardcoded secrets. All sensitive data (GitHub Private Keys, Webhook Secrets, Gemini API Keys) must be stored in AWS Secrets Manager or Systems Manager (SSM) Parameter Store. Webhook signatures must be rigorously verified before processing.

## 3. Technical Constraints
*   **Language:** Python (FastAPI with Mangum for Lambda integration) or Go for optimal cold-start performance.
*   **Infrastructure:** AWS Serverless (Lambda, API Gateway/Function URLs, IAM, SSM). Infrastructure as Code (IaC) via Terraform.
*   **Cost:** Minimal. Leverages the AWS Free Tier for Lambda and the existing Google AI Pro API grants.
*   **Speed:** Target response time for the webhook acknowledgment is < 3 seconds (as required by GitHub). The actual review can be processed asynchronously if needed, though Gemini's speed may allow synchronous processing for smaller diffs.
