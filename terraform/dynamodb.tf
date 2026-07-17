resource "aws_dynamodb_table" "state" {
  name                        = "${var.project_name}-state"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "pk"
  deletion_protection_enabled = false

  attribute {
    name = "pk"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }
}
