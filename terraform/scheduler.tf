resource "aws_scheduler_schedule" "daily" {
  name                         = "${var.project_name}-daily"
  description                  = "Daily Weather Pulse NZ trigger at 06:30 Pacific/Auckland"
  schedule_expression          = "cron(30 6 * * ? *)"
  schedule_expression_timezone = "Pacific/Auckland"
  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.agent.arn
    role_arn = aws_iam_role.scheduler.arn

    retry_policy {
      maximum_event_age_in_seconds = 300
      maximum_retry_attempts       = 2
    }
  }
}

resource "aws_lambda_permission" "allow_scheduler" {
  statement_id  = "AllowExecutionFromScheduler"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.agent.function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = aws_scheduler_schedule.daily.arn
}
