# Weather Pulse NZ — Smoke Runbook & Silent Demo Script

## Theme

Daily NZ weather & air quality agent — email, Slack, and HTML report.

## Overview

Silent product demo focused on architecture and shiny outputs.

Compiled locally: [`captures/weather-pulse-nz-demo.mp4`](captures/weather-pulse-nz-demo.mp4)

Published: [https://youtu.be/cfpqOgOjKOI](https://youtu.be/cfpqOgOjKOI)

```bash
# from repo root (venv with playwright + pillow)
.venv/bin/python -m playwright install chromium   # once
export REPORT_URL="$(cd terraform && terraform output -raw report_link_url)"
cd docs/demo/captures
../../../.venv/bin/python capture-report.py
# architecture PNG (optional re-export):
# docker run --rm -v "$PWD/../..":/data rlespinasse/drawio-desktop-headless \
#   -x -f png -o /data/demo/captures/arch.png /data/weather-pulse-nz-architecture.drawio
../../../.venv/bin/python build-demo.py
```

---

## Beat Table

| # | Beat | Caption | Source |
| - | ---- | ------- | ------ |
| 1 | Title | Weekend Agent Challenge: Weather Pulse NZ | generated |
| 2 | Product | Open-Meteo → briefing → email, Slack, report | generated |
| 3 | Architecture | scheduled serverless in ap-southeast-2 | [arch.png](captures/arch.png) |
| 4 | Email | SNS daily briefing in your inbox | [email.png](captures/email.png) |
| 5 | Slack | mood-colored digest | [slack.png](captures/slack.png) |
| 6 | Report · 1 | executive brief | [report-01-brief.png](captures/report-01-brief.png) |
| 7 | Report · 2 | city snapshot board | [report-02-cities.png](captures/report-02-cities.png) |
| 8 | Report · 3 | extremes · AQI · deltas | [report-03-extremes.png](captures/report-03-extremes.png) |
| 9 | Schedule | 06:30 Wellington · 8 NZ cities | generated |
| 10 | Close | Built with Kiro | generated |

---

## Smoke (product)

1. Confirm Lambda can invoke successfully (`statusCode: 200`, report URL present).
2. Confirm SNS email and Slack digest arrived for the same run.
3. Open `terraform output -raw report_link_url` — hero, city board, extremes all render.
4. Rebuild stills and MP4 with the commands above.

## Capture notes

- **Email / Slack:** provided stills (`email.png`, `slack.png`).
- **Report:** Playwright (`capture-report.py`) screenshots three section groups covering the full HTML page.
- **Architecture:** PNG export of `docs/weather-pulse-nz-architecture.drawio` → `captures/arch.png`.
