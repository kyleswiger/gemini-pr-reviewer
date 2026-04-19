# Gemini PR Reviewer

A blazing-fast, secure, and cost-effective GitHub PR Review automation tool powered by Google's Gemini API and AWS Serverless infrastructure.

## Why this tool?
Current solutions like Gemini Code Assist can be slow or rely on older model versions. This tool is built to use your own Google AI Pro API grants to access the latest models (like Gemini 1.5 Pro). Furthermore, it is designed with a **bi-directional AI workflow** in mind: it structures its feedback so that local AI assistants like Cursor and Claude can easily ingest the review comments and automatically apply the suggested fixes.

## Features
*   **Latest Gemini Models:** Bring your own API key to utilize the bleeding-edge Google AI models.
*   **Cursor/Claude Optimized:** Reviews are formatted specifically to be easily parsed and applied by your local AI IDE.
*   **Serverless & Cheap:** Runs on AWS Lambda. You only pay for the milliseconds it takes to run, leveraging AWS's generous free tier. No persistent servers required.
*   **Secure:** Built for public release. Secrets are fetched securely at runtime via AWS SSM or Secrets Manager. Webhook payloads are strictly verified.

## Getting Started
(Deployment instructions and Terraform configuration coming soon in Phase 1.)
