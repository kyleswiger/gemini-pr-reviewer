output "webhook_url" {
  description = "Base Function URL. Register <webhook_url>webhook as the GitHub webhook target."
  value       = aws_lambda_function_url.webhook.function_url
}

output "lambda_function_name" {
  description = "Deployed Lambda function name."
  value       = aws_lambda_function.webhook.function_name
}

output "lambda_role_arn" {
  description = "IAM role assumed by the Lambda."
  value       = aws_iam_role.lambda_exec.arn
}

output "cloudwatch_log_group" {
  description = "CloudWatch log group for the Lambda."
  value       = aws_cloudwatch_log_group.lambda.name
}
