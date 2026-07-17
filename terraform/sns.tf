resource "aws_sns_topic" "digest" {
  name = "${var.project_name}-digest"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.digest.arn
  protocol  = "email"
  endpoint  = var.email_subscription
}
