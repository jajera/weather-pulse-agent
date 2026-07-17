# Weather Pulse NZ — Demo

Silent product walkthrough for general audiences.

| File | Purpose |
|------|---------|
| [video-slideshow.md](video-slideshow.md) | Beat table, smoke checklist, rebuild commands |
| [builder-center-post.md](builder-center-post.md) | Paste-ready AWS Builder Center article |
| [captures/](captures/) | Stills + `capture-report.py` + `build-demo.py` |
| [captures/weather-pulse-nz-demo.mp4](captures/weather-pulse-nz-demo.mp4) | Compiled silent demo |

## Rebuild

```bash
# from repo root
.venv/bin/python -m playwright install chromium   # once
export REPORT_URL="$(cd terraform && terraform output -raw report_link_url)"
cd docs/demo/captures
../../../.venv/bin/python capture-report.py
../../../.venv/bin/python build-demo.py
```

## Demo video

[https://youtu.be/cfpqOgOjKOI](https://youtu.be/cfpqOgOjKOI)
