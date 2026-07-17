output "s3_bucket_name" {
  description = "Report bucket name"
  value       = aws_s3_bucket.reports.bucket
}

output "report_link_url" {
  description = "Short public report link (Lambda Function URL proxies private S3 HTML)"
  value       = "${aws_lambda_function_url.report_link.function_url}report"
}

output "s3_report_key" {
  description = "Private HTML report object key"
  value       = "s3://${aws_s3_bucket.reports.bucket}/reports/latest.html"
}

output "sns_topic_arn" {
  description = "SNS digest topic ARN"
  value       = aws_sns_topic.digest.arn
}

output "lambda_function_arn" {
  description = "Weather Pulse Lambda ARN"
  value       = aws_lambda_function.agent.arn
}

output "dynamodb_table_name" {
  description = "State store table name"
  value       = aws_dynamodb_table.state.name
}
