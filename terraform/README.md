# Weather Pulse NZ Terraform

## Prerequisites

1. Choose a globally unique S3 bucket name.
2. Copy the example vars file and edit it:

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Terraform automatically loads `terraform.tfvars` (gitignored).

## Variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `aws_region` | No | `ap-southeast-2` | AWS region for all resources |
| `project_name` | No | `weather-pulse` | Resource naming prefix |
| `environment` | No | `prod` | Environment tag value |
| `email_subscription` | Yes | None | SNS email recipient for the digest |
| `s3_bucket_name` | Yes | None | Globally unique bucket for reports and raw archives |

## Usage

```bash
cd terraform
terraform init
terraform validate
terraform plan
terraform apply
```

Confirm the SNS email subscription from your inbox after apply.

Useful outputs after apply:

```bash
terraform output report_link_url
terraform output lambda_function_arn
```

Manual invoke (empty payload runs the daily pipeline):

```bash
aws lambda invoke \
  --function-name weather-pulse-nz \
  --region ap-southeast-2 \
  --cli-binary-format raw-in-base64-out \
  --payload '{}' \
  /tmp/weather-pulse-out.json
```

Full operator steps: [docs/runbook.md](../docs/runbook.md).

Destroy is safe for filled resources: the S3 bucket uses `force_destroy = true` (objects are removed on destroy), and DynamoDB deletion protection is off.

The bucket stays private. Slack/email use a **short Function URL** that **serves** the HTML report (no browser redirect to a long S3 signature URL).

**Link validity**
- Short link (`…lambda-url…/report`): stays usable while the stack is deployed; Lambda reads the private S3 object with IAM
- Pre-signed S3 URLs are only a fallback if the Function URL base is missing from SSM

**Brand assets** (favicon / Open Graph) are served from the same Function URL:
- `…/favicon.svg`, `…/favicon.png`
- `…/og.jpg` (1200×630 social preview)

## Slack webhook SSM

Terraform creates `/weather-pulse/slack-webhook` as a SecureString with a placeholder.
After apply, set the real webhook URL manually (Terraform ignores value changes):

```bash
aws ssm put-parameter \
  --name /weather-pulse/slack-webhook \
  --type SecureString \
  --value 'https://hooks.slack.com/services/...' \
  --overwrite \
  --region ap-southeast-2
```

## Related docs

- [docs/runbook.md](../docs/runbook.md) — deploy, invoke, verify, and troubleshoot
- [docs/architecture.md](../docs/architecture.md) — how the pieces fit
- [docs/weather-pulse-nz-architecture.drawio](../docs/weather-pulse-nz-architecture.drawio) — official AWS icon diagram
