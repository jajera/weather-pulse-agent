data "external" "lambda_package" {
  program = ["python3", "${path.module}/package_lambda.py"]
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.project_name}-nz"
  retention_in_days = 14
}

resource "aws_lambda_function" "agent" {
  function_name = "${var.project_name}-nz"
  role          = aws_iam_role.lambda.arn
  handler       = "src.handler.handler"
  runtime       = "python3.14"
  timeout       = 120
  memory_size   = 256

  filename         = data.external.lambda_package.result.path
  source_code_hash = data.external.lambda_package.result.base64sha256

  environment {
    variables = {
      SNS_TOPIC_ARN            = aws_sns_topic.digest.arn
      S3_BUCKET                = aws_s3_bucket.reports.bucket
      DYNAMODB_TABLE           = aws_dynamodb_table.state.name
      SSM_SLACK_WEBHOOK_PARAM  = aws_ssm_parameter.slack_webhook.name
      SSM_REPORT_LINK_PARAM    = "/weather-pulse/report-link-url"
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda,
    aws_cloudwatch_log_group.lambda,
  ]
}

resource "aws_lambda_function_url" "report_link" {
  function_name      = aws_lambda_function.agent.function_name
  authorization_type = "NONE"

  cors {
    allow_origins = ["*"]
    allow_methods = ["GET"]
  }
}
