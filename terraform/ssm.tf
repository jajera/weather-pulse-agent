# Creates the Slack webhook SecureString shell. Value is set/updated manually
# after apply; Terraform ignores value drift so plan/apply will not overwrite it.

resource "aws_ssm_parameter" "slack_webhook" {
  name        = "/weather-pulse/slack-webhook"
  description = "Slack Incoming Webhook URL for Weather Pulse NZ (set manually)"
  type        = "SecureString"
  value       = "PLACEHOLDER_UPDATE_MANUALLY"

  lifecycle {
    ignore_changes = [value]
  }
}

# Short report link base (Lambda Function URL). Written by Terraform; read by Lambda.
resource "aws_ssm_parameter" "report_link" {
  name        = "/weather-pulse/report-link-url"
  description = "Short public report link base (Lambda Function URL)"
  type        = "String"
  value       = trimsuffix(aws_lambda_function_url.report_link.function_url, "/")
}
