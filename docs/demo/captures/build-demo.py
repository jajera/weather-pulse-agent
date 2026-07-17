#!/usr/bin/env python3
"""Rebuild Weather Pulse NZ silent demo MP4 from captures. Intermediates → _build/."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BUILD = HERE / "_build"
W, H = 1440, 1080
BG = (0, 0, 0)
TEAL = (56, 189, 168)
WHITE = (245, 248, 250)
MUTED = (170, 178, 186)
ACCENT = (120, 220, 200)
CARD_SECS = 3
CONTENT_SECS = 6
ARCH_SECS = 7
REPORT_SECS = 7
OUT = HERE / "weather-pulse-nz-demo.mp4"

SRC = {
    "arch": HERE / "arch.png",
    "email": HERE / "email.png",
    "slack": HERE / "slack.png",
    "brief": HERE / "report-01-brief.png",
    "cities": HERE / "report-02-cities.png",
    "extremes": HERE / "report-03-extremes.png",
}


def font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/montserrat-fonts/Montserrat-Bold.ttf"
        if bold
        else "/usr/share/fonts/montserrat-fonts/Montserrat-Regular.ttf",
        "/usr/share/fonts/google-noto/NotoSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/google-noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/abattis-cantarell/Cantarell-Bold.otf"
        if bold
        else "/usr/share/fonts/abattis-cantarell/Cantarell-Regular.otf",
        "/usr/share/fonts/liberation-sans/LiberationSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/liberation-sans/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_centered(draw, lines, gap: int = 18) -> None:
    measured = []
    total_h = 0
    for text, fnt, color in lines:
        bbox = draw.textbbox((0, 0), text, font=fnt)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        measured.append((text, fnt, color, tw, th))
        total_h += th + gap
    total_h -= gap
    y = (H - total_h) // 2
    for text, fnt, color, tw, th in measured:
        draw.text(((W - tw) // 2, y), text, font=fnt, fill=color)
        y += th + gap


def black_card(path: Path, lines) -> None:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, 8], fill=TEAL)
    draw.rectangle([0, H - 8, W, H], fill=TEAL)
    draw_centered(draw, lines)
    img.save(path)


def fit_on_black(src_path: Path, out_path: Path) -> None:
    src = Image.open(src_path).convert("RGBA")
    scale = min(W / src.width, H / src.height)
    nw, nh = max(1, int(src.width * scale)), max(1, int(src.height * scale))
    src = src.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (W, H), BG)
    canvas.paste(src, ((W - nw) // 2, (H - nh) // 2), src)
    canvas.save(out_path)


def pick_encoder() -> str:
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if "libx264" in out:
        return "libx264"
    if "libopenh264" in out:
        return "libopenh264"
    raise SystemExit("No H.264 encoder (need libx264 or libopenh264)")


def build_assets() -> None:
    BUILD.mkdir(exist_ok=True)
    title_f = font(64, True)
    sub_f = font(36, True)
    body_f = font(32)

    black_card(
        BUILD / "title.png",
        [
            ("Weekend Agent Challenge:", sub_f, MUTED),
            ("Weather Pulse NZ", title_f, WHITE),
            ("daily NZ weather agent", body_f, ACCENT),
        ],
    )
    black_card(
        BUILD / "card-product.png",
        [
            ("What you get", title_f, WHITE),
            ("Open-Meteo → briefing → email, Slack, report", body_f, ACCENT),
        ],
    )
    black_card(
        BUILD / "card-arch.png",
        [
            ("Architecture at a glance", title_f, WHITE),
            ("scheduled serverless in ap-southeast-2", body_f, ACCENT),
        ],
    )
    black_card(
        BUILD / "card-email.png",
        [
            ("Email gets the briefing", title_f, WHITE),
            ("SNS daily digest in your inbox", body_f, ACCENT),
        ],
    )
    black_card(
        BUILD / "card-slack.png",
        [
            ("Slack gets the pulse", title_f, WHITE),
            ("mood-colored daily digest", body_f, ACCENT),
        ],
    )
    black_card(
        BUILD / "card-brief.png",
        [
            ("Report · executive brief", title_f, WHITE),
            ("headline · watchouts", body_f, ACCENT),
        ],
    )
    black_card(
        BUILD / "card-cities.png",
        [
            ("Report · city board", title_f, WHITE),
            ("eight NZ cities at a glance", body_f, ACCENT),
        ],
    )
    black_card(
        BUILD / "card-extremes.png",
        [
            ("Report · extremes & air quality", title_f, WHITE),
            ("extremes · AQI · deltas", body_f, ACCENT),
        ],
    )
    black_card(
        BUILD / "card-schedule.png",
        [
            ("Every morning at 06:30 Wellington", title_f, WHITE),
            (
                "Auckland · Hamilton · Tauranga · Wellington",
                body_f,
                MUTED,
            ),
            (
                "Nelson · Christchurch · Queenstown · Dunedin",
                body_f,
                MUTED,
            ),
        ],
    )
    black_card(
        BUILD / "end.png",
        [
            ("Built with Kiro", title_f, WHITE),
            ("#BuildWithKiro #TeamKiro @kirodotdev", body_f, WHITE),
        ],
    )

    for key, src in SRC.items():
        if not src.exists():
            raise SystemExit(f"Missing source capture: {src.name}")
        fit_on_black(src, BUILD / f"slide-{key}.png")


def run_ffmpeg(encoder: str) -> None:
    inputs = [
        ("title.png", CARD_SECS),
        ("card-product.png", CARD_SECS),
        ("card-arch.png", CARD_SECS),
        ("slide-arch.png", ARCH_SECS),
        ("card-email.png", CARD_SECS),
        ("slide-email.png", CONTENT_SECS),
        ("card-slack.png", CARD_SECS),
        ("slide-slack.png", CONTENT_SECS),
        ("card-brief.png", CARD_SECS),
        ("slide-brief.png", CONTENT_SECS),
        ("card-cities.png", CARD_SECS),
        ("slide-cities.png", REPORT_SECS),
        ("card-extremes.png", CARD_SECS),
        ("slide-extremes.png", REPORT_SECS),
        ("card-schedule.png", CARD_SECS),
        ("end.png", CARD_SECS),
    ]
    # ~3+3+3+7 + 3+6 + 3+6 + 3+6 + 3+7 + 3+7 + 3+3 = 69s

    cmd: list[str] = ["ffmpeg", "-y"]
    for name, secs in inputs:
        cmd += ["-loop", "1", "-t", str(secs), "-i", name]

    n = len(inputs)
    filters = []
    for i in range(n):
        filters.append(f"[{i}:v]scale={W}:{H},setsar=1,fps=30,format=yuv420p[v{i}]")
    concat_in = "".join(f"[v{i}]" for i in range(n))
    filters.append(f"{concat_in}concat=n={n}:v=1:a=0[outv]")
    filter_complex = ";".join(filters)

    cmd += [
        "-filter_complex",
        filter_complex,
        "-map",
        "[outv]",
        "-an",
        "-c:v",
        encoder,
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(OUT),
    ]
    if encoder == "libx264":
        i = cmd.index("libx264")
        cmd[i + 1 : i + 1] = ["-preset", "medium", "-crf", "20"]
    else:
        cmd += ["-b:v", "2500k"]

    print(f"Encoding {n} segments → {OUT.name}")
    subprocess.run(cmd, cwd=BUILD, check=True)
    print(f"Wrote {OUT}")


def main() -> None:
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found on PATH")
    encoder = pick_encoder()
    print(f"Using encoder: {encoder}")
    build_assets()
    run_ffmpeg(encoder)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
