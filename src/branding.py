"""Favicon and Open Graph assets for the HTML report."""

from __future__ import annotations

import base64
from importlib import resources
from pathlib import Path
from urllib.parse import quote

_ASSETS = Path(__file__).resolve().parent / "assets"

FAVICON_SVG = (_ASSETS / "favicon.svg").read_text(encoding="utf-8")


def favicon_data_uri() -> str:
    """Inline SVG favicon so the browser tab works even on pre-signed S3 HTML."""
    return "data:image/svg+xml," + quote(FAVICON_SVG.strip())


def _read_bytes(name: str) -> bytes:
    path = _ASSETS / name
    if path.is_file():
        return path.read_bytes()
    # Fallback for odd packaging layouts
    return resources.files("src.assets").joinpath(name).read_bytes()


def favicon_png_bytes() -> bytes:
    return _read_bytes("favicon.png")


def og_image_bytes() -> bytes:
    return _read_bytes("og.jpg")


def favicon_png_data_uri() -> str:
    encoded = base64.b64encode(favicon_png_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"
