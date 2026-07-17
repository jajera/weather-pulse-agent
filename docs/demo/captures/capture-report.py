#!/usr/bin/env python3
"""Capture the live HTML report as three section-group PNGs via Playwright."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

SLIDES = [
    {
        "file": "report-01-brief.png",
        "selectors": ["header.hero", "#executive-brief"],
    },
    {
        "file": "report-02-cities.png",
        "selectors": ["#city-snapshot-board"],
    },
    {
        "file": "report-03-extremes.png",
        "selectors": [
            "#nz-extremes",
            "#air-quality-watch",
            "#delta-vs-last-run",
            "#sources-and-attribution",
        ],
    },
]


def resolve_report_url() -> str:
    env = os.environ.get("REPORT_URL", "").strip()
    if env:
        return env
    tf = REPO / "terraform"
    try:
        out = subprocess.run(
            ["terraform", "output", "-raw", "report_link_url"],
            cwd=tf,
            check=True,
            capture_output=True,
            text=True,
        )
        url = out.stdout.strip()
        if url:
            return url
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise SystemExit(
            "Set REPORT_URL or run from a tree with terraform output report_link_url"
        ) from exc
    raise SystemExit("Empty report_link_url")


def main() -> None:
    url = resolve_report_url()
    print(f"Capturing report: {url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1280, "height": 900},
            device_scale_factor=2,
        )
        page.goto(url, wait_until="networkidle", timeout=60_000)
        page.wait_for_selector("header.hero", timeout=30_000)
        page.wait_for_selector("#city-snapshot-board", timeout=30_000)

        for slide in SLIDES:
            selectors = slide["selectors"]
            # Wrap matched nodes in a temporary container for one clean screenshot
            page.evaluate(
                """(sels) => {
                  document.querySelectorAll('[data-demo-wrap]').forEach((el) => {
                    const parent = el.parentNode;
                    while (el.firstChild) parent.insertBefore(el.firstChild, el);
                    parent.removeChild(el);
                  });
                  const nodes = sels.map((s) => document.querySelector(s)).filter(Boolean);
                  if (!nodes.length) throw new Error('No nodes for ' + sels.join(','));
                  const wrap = document.createElement('div');
                  wrap.setAttribute('data-demo-wrap', '1');
                  wrap.style.cssText =
                    'display:block;padding:16px;background:inherit;box-sizing:border-box;';
                  const first = nodes[0];
                  first.parentNode.insertBefore(wrap, first);
                  nodes.forEach((n) => wrap.appendChild(n));
                }""",
                selectors,
            )
            page.locator("[data-demo-wrap]").screenshot(
                path=str(HERE / slide["file"]),
                type="png",
            )
            # Unwrap so subsequent slides still find original section IDs in DOM order
            page.evaluate(
                """() => {
                  document.querySelectorAll('[data-demo-wrap]').forEach((el) => {
                    const parent = el.parentNode;
                    while (el.firstChild) parent.insertBefore(el.firstChild, el);
                    parent.removeChild(el);
                  });
                }"""
            )
            print(f"Wrote {slide['file']}")

        browser.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 — surface capture failures clearly
        print(f"capture-report failed: {exc}", file=sys.stderr)
        sys.exit(1)
