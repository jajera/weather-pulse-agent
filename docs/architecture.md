# Architecture

Weather Pulse NZ is a scheduled serverless agent in **ap-southeast-2**. Once a day it fetches NZ city weather and air quality, compares against the previous run, generates a short briefing, and delivers it to email, Slack, and a private HTML report.

## Diagram

Official AWS Architecture Icons ([jajera.github.io/aws-icons](https://jajera.github.io/aws-icons/)) in draw.io format:

- **File:** [`weather-pulse-nz-architecture.drawio`](./weather-pulse-nz-architecture.drawio)
- Open locally in [diagrams.net](https://app.diagrams.net/) (**File → Open from… → Device**) or VS Code Draw.io extension

```text
EventBridge Scheduler (06:30 NZ)
        │
        ▼
   Open-Meteo - - ► AWS Lambda (forecast + AQI) ← dashed: external
        │
        ├──── DynamoDB (last-run snapshot / deltas)
        ├──── Amazon Bedrock Claude 3 Haiku (template fallback)
        ├──── S3 private reports/ + raw/
        ├──── SSM Parameter Store (Slack webhook + report URL)
        ├──── SNS - - ► email inbox              ← dashed: external
        └──── Slack Incoming Webhook             ← dashed: external

Readers - - GET /report - ► Lambda Function URL ──GetObject──► S3
                 (non-GET → 405)                ← dashed: external

Legend: ──── AWS-internal   - - ► crosses AWS boundary
```

## Components

| Piece | Role |
|-------|------|
| **EventBridge Scheduler** | Daily invoke at 06:30 `Pacific/Auckland` |
| **Lambda** (`weather-pulse-nz`) | Pipeline + public Function URL for report/assets |
| **Open-Meteo** | Forecast and US AQI for 8 NZ cities |
| **DynamoDB** | Last-run snapshot for delta / mood |
| **Amazon Bedrock** | Narrative digest (Claude 3 Haiku); mood always from delta thresholds |
| **S3** | Private `reports/latest.html` + dated `raw/` JSON |
| **SSM Parameter Store** | Slack webhook (SecureString); report link URL |
| **SNS** | Email subscription for the digest |
| **Slack** | Mood-colored Incoming Webhook message |

## Report link model

- Bucket stays **private**.
- Notifications use a short **Lambda Function URL** (`…/report`).
- GET serves HTML (and `/favicon.svg`, `/og.jpg`) by reading S3 with IAM.
- Non-GET on the Function URL returns **405** so the public URL cannot trigger the daily pipeline.

## Specs

Product requirements and design details: [`.kiro/specs/weather-pulse-nz/`](../.kiro/specs/weather-pulse-nz/).
