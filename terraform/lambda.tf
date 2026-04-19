# -----------------------------------------------------------------------------
# Package the Lambda: install deps into a staging dir, layer in source, zip.
# -----------------------------------------------------------------------------
resource "null_resource" "lambda_build" {
  triggers = {
    src_hash = local.src_hash
  }

  provisioner "local-exec" {
    interpreter = ["bash", "-c"]
    command     = <<-EOT
      set -euo pipefail
      rm -rf "${local.build_dir}/package"
      mkdir -p "${local.build_dir}/package"
      pip install \
        --platform manylinux2014_${var.lambda_architecture == "arm64" ? "aarch64" : "x86_64"} \
        --target "${local.build_dir}/package" \
        --implementation cp \
        --python-version 3.12 \
        --only-binary=:all: \
        --upgrade \
        --quiet \
        -r "${local.src_dir}/requirements.txt"
      cp "${local.src_dir}"/*.py "${local.build_dir}/package/"
    EOT
  }
}

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${local.build_dir}/package"
  output_path = local.zip_path

  depends_on = [null_resource.lambda_build]
}

# -----------------------------------------------------------------------------
# IAM: execution role with CloudWatch logs + scoped SSM read.
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_exec" {
  name               = "${var.project_name}-lambda-exec"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "lambda_ssm_read" {
  statement {
    sid    = "ReadProjectSsmParameters"
    effect = "Allow"
    actions = [
      "ssm:GetParameter",
      "ssm:GetParameters",
      "ssm:GetParametersByPath",
    ]
    resources = [
      "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter${var.ssm_parameter_prefix}",
      "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter${var.ssm_parameter_prefix}/*",
    ]
  }

  statement {
    sid       = "DecryptSsmSecureStrings"
    effect    = "Allow"
    actions   = ["kms:Decrypt"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${data.aws_region.current.name}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "lambda_ssm_read" {
  name   = "${var.project_name}-ssm-read"
  role   = aws_iam_role.lambda_exec.id
  policy = data.aws_iam_policy_document.lambda_ssm_read.json
}

# -----------------------------------------------------------------------------
# CloudWatch log group (explicit so we control retention).
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.project_name}"
  retention_in_days = var.log_retention_days
}

# -----------------------------------------------------------------------------
# Lambda function + public Function URL (auth handled in-app via HMAC).
# -----------------------------------------------------------------------------
resource "aws_lambda_function" "webhook" {
  function_name    = var.project_name
  role             = aws_iam_role.lambda_exec.arn
  handler          = "main.handler"
  runtime          = var.lambda_runtime
  architectures    = [var.lambda_architecture]
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout          = var.lambda_timeout_seconds
  memory_size      = var.lambda_memory_mb

  environment {
    variables = {
      SSM_PARAMETER_PREFIX = var.ssm_parameter_prefix
      LOG_LEVEL            = "INFO"
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy_attachment.lambda_basic,
    aws_iam_role_policy.lambda_ssm_read,
  ]
}

resource "aws_lambda_function_url" "webhook" {
  function_name      = aws_lambda_function.webhook.function_name
  authorization_type = "NONE" # GitHub webhooks authenticate via HMAC inside the handler.
}
