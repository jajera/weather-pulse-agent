# weather-pulse-agent

Always-on AWS agent that pulls Open-Meteo NZ weather and air quality, then posts a daily briefing to **Slack**, **email (SNS)**, and a **private HTML report**.

## What you get

- **Schedule:** every day at **06:30** `Pacific/Auckland`
- **Cities:** Auckland, Hamilton, Tauranga, Wellington, Nelson, Christchurch, Queenstown, Dunedin
- **Digest:** Amazon Bedrock Claude 3 Haiku (template fallback), mood from thresholds/deltas
- **Report:** short Function URL (`…/report`) that proxies private S3 HTML — no long pre-signed URL in the address bar

## Stack

| Layer | Choice |
|-------|--------|
| Runtime | AWS Lambda (Python 3.14), 120s, `ap-southeast-2` |
| Trigger | EventBridge Scheduler |
| State | DynamoDB last-run snapshot |
| Storage | Private S3 (`reports/`, `raw/`) |
| Notify | SNS email + Slack Incoming Webhook (SSM Parameter Store) |
| AI | Amazon Bedrock Claude 3 Haiku |

## Docs

| Doc | Use when |
|-----|----------|
| [docs/runbook.md](docs/runbook.md) | Deploy, invoke, verify, troubleshoot |
| [docs/architecture.md](docs/architecture.md) | How the pieces fit |
| [docs/weather-pulse-nz-architecture.drawio](docs/weather-pulse-nz-architecture.drawio) | Official AWS icon diagram (draw.io) |
| [docs/demo/](docs/demo/) | Silent product walkthrough (slideshow → MP4) |
| [terraform/README.md](terraform/README.md) | Terraform vars and apply |
| [`.kiro/specs/weather-pulse-nz/`](.kiro/specs/weather-pulse-nz/) | Requirements, design, tasks |

## Local development

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r dev-requirements.txt
pytest
```

## Deploy

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # set email + unique bucket
terraform init
terraform validate
terraform plan
terraform apply
```

Then confirm the SNS email and set the Slack webhook — see the [runbook](docs/runbook.md).

## Operations

- **Logs:** CloudWatch log group `/aws/lambda/weather-pulse-nz`
- **Retries:** Scheduler retries up to 2 times in a 5-minute window
- **Abuse guard:** Function URL accepts `GET /report`; non-GET returns `405`

## Cost and Scale Notes

- Designed for low steady-state cost (one scheduled run per day).
- Main recurring charges are Lambda, S3 storage/requests, DynamoDB on-demand ops, and Bedrock inference.
- Set CloudWatch alarms for Lambda errors and duration if you need stronger operational guardrails.
