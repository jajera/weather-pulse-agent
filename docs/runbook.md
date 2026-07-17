# Runbook — Weather Pulse NZ

Operator guide for deploy, verify, and common failures.

## Prerequisites

- AWS account with rights to create Lambda, S3, DynamoDB, SNS, SSM, IAM, EventBridge Scheduler
- **Bedrock** model access in `ap-southeast-2` for `anthropic.claude-3-haiku-20240307-v1:0` (template fallback still works without it)
- Globally unique S3 bucket name
- Slack Incoming Webhook URL (optional until you set it in SSM Parameter Store)
- Email address for SNS subscription

## Deploy

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# edit: email_subscription, s3_bucket_name, etc.

terraform init
terraform validate
terraform plan
terraform apply
```

After apply:

1. Confirm the **SNS email** subscription from your inbox.
2. Set the Slack webhook (Terraform leaves a placeholder; value is ignored on later applies):

```bash
aws ssm put-parameter \
  --name /weather-pulse/slack-webhook \
  --type SecureString \
  --value 'https://hooks.slack.com/services/...' \
  --overwrite \
  --region ap-southeast-2
```

3. Note outputs:

```bash
terraform output report_link_url
terraform output lambda_function_arn
```

## Manual run

```bash
aws lambda invoke \
  --function-name weather-pulse-nz \
  --region ap-southeast-2 \
  --cli-binary-format raw-in-base64-out \
  --payload '{}' \
  /tmp/weather-pulse-out.json

cat /tmp/weather-pulse-out.json
```

Expect `statusCode: 200`, a `mood`, and usually a `report_url`.

## Verify

| Check | How |
|-------|-----|
| Logs | CloudWatch log group `/aws/lambda/weather-pulse-nz` |
| Email | SNS digest with short `…/report` link (or “unavailable” if HTML write failed) |
| Slack | Mood-colored attachment + “View full report” |
| Report | Open `terraform output -raw report_link_url` — address bar stays on Function URL |
| Favicon / OG | `…/favicon.svg`, `…/og.jpg` |
| Abuse guard | `curl -X POST "$FUNCTION_URL"` → **405** |

## Observability baseline

- Track `/aws/lambda/weather-pulse-nz` for errors, retries, and report-link proxy logs.
- Create CloudWatch alarms for:
  - Lambda `Errors > 0` for 1 datapoint
  - Lambda duration near timeout (for example `Duration > 100000 ms`)
  - Scheduler delivery failures (EventBridge Scheduler metrics)

## Schedule

- Expression: `cron(30 6 * * ? *)`
- Timezone: `Pacific/Auckland` (NZST/NZDT)
- Retries: up to 2 within 5 minutes on invoke failure

## Common failures

| Symptom | Likely cause | What to do |
|---------|--------------|------------|
| Digest sounds templated / “no major change” copy | Bedrock denied or timeout | Check IAM + model access; template path is expected fallback |
| Mood quiet but AQI looks bad on first day | Fixed in current code — redeploy if on a previous deployment | `terraform apply` then re-invoke |
| Email/Slack say report unavailable | S3 `PutObject` for HTML failed | Check Lambda S3 IAM + bucket name env |
| Report link 502 | Object missing or GetObject denied | Run a successful pipeline once; check IAM GetObject |
| POST to Function URL runs digests | Old code without 405 gate | Redeploy current handler |
| No Slack | Webhook still placeholder / SSM missing | `put-parameter` as above |
| No email | SNS subscription not confirmed | Confirm from email |

## Useful commands

```bash
# Tail recent logs
aws logs tail /aws/lambda/weather-pulse-nz --region ap-southeast-2 --since 1h

# Function URL (from console or)
aws lambda get-function-url-config \
  --function-name weather-pulse-nz \
  --region ap-southeast-2

# Destroy stack (bucket force_destroy=true)
cd terraform && terraform destroy
```

## Related docs

- [Architecture](./architecture.md) + draw.io diagram
- [Terraform README](../terraform/README.md)
- Specs: [`.kiro/specs/weather-pulse-nz/`](../.kiro/specs/weather-pulse-nz/)
