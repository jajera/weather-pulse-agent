"""S3 raw JSON archive and HTML report writer."""

from __future__ import annotations

import html
import json
import logging
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from src.branding import favicon_data_uri
from src.config import (
    AWS_REGION,
    HTML_REPORT_KEY,
    REPORT_PRESIGN_EXPIRES_SECONDS,
    S3_BUCKET,
    WATCHED_CITIES,
)
from src.report_link import report_link_base

logger = logging.getLogger(__name__)

MOOD_THEME = {
    "quiet": {"accent": "#2eb886", "bg": "#e8f8f2", "label": "Quiet"},
    "notable": {"accent": "#ecb22e", "bg": "#fff6e0", "label": "Notable"},
    "severe": {"accent": "#e01e5a", "bg": "#fde8ef", "label": "Severe"},
}


def _utc_raw_key(run_timestamp: datetime) -> str:
    utc = run_timestamp.astimezone(timezone.utc)
    return f"raw/{utc.strftime('%Y-%m-%dT%H%MZ')}.json"


def presign_report_url(
    expires_in: int = REPORT_PRESIGN_EXPIRES_SECONDS,
) -> str:
    """Return a time-limited GET URL for reports/latest.html."""
    client = boto3.client("s3", region_name=AWS_REGION)
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET, "Key": HTML_REPORT_KEY},
        ExpiresIn=expires_in,
    )


def read_html_report() -> str:
    """Load the latest HTML report body from S3 (for Function URL proxying)."""
    client = boto3.client("s3", region_name=AWS_REGION)
    response = client.get_object(Bucket=S3_BUCKET, Key=HTML_REPORT_KEY)
    return response["Body"].read().decode("utf-8")


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    return html.escape(str(value))


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def weather_icon(code: Any) -> tuple[str, str]:
    """Map WMO weather code to (emoji, short label)."""
    try:
        c = int(code)
    except (TypeError, ValueError):
        return "🌡️", "Unknown"
    if c == 0:
        return "☀️", "Clear"
    if c in {1, 2}:
        return "🌤️", "Mostly clear"
    if c == 3:
        return "☁️", "Overcast"
    if c in {45, 48}:
        return "🌫️", "Fog"
    if c in {51, 53, 55, 56, 57}:
        return "🌦️", "Drizzle"
    if c in {61, 63, 65, 66, 67}:
        return "🌧️", "Rain"
    if c in {71, 73, 75, 77}:
        return "❄️", "Snow"
    if c in {80, 81, 82}:
        return "🌧️", "Showers"
    if c in {85, 86}:
        return "🌨️", "Snow showers"
    if c in {95, 96, 99}:
        return "⛈️", "Thunder"
    return "🌡️", f"Code {c}"


def _aqi_badge(aqi: float | None) -> str:
    if aqi is None:
        return '<span class="badge muted">AQI —</span>'
    if aqi >= 150:
        cls, label = "bad", "Unhealthy"
    elif aqi >= 100:
        cls, label = "warn", "Watch"
    elif aqi >= 50:
        cls, label = "ok", "Moderate"
    else:
        cls, label = "good", "Good"
    return f'<span class="badge {cls}">{label} {aqi:.0f}</span>'


def _gust_badge(gust: float | None) -> str:
    if gust is None:
        return "—"
    if gust >= 40:
        return f'<span class="badge warn">{gust:.1f}</span>'
    return f"{gust:.1f}"


def _temp_cell(value: float | None, *, cold: bool = False) -> str:
    if value is None:
        return "—"
    if cold and value <= 2:
        return f'<span class="temp-cold">{value:.1f}</span>'
    if not cold and value >= 20:
        return f'<span class="temp-hot">{value:.1f}</span>'
    return f"{value:.1f}"


def _list_or_none(items: list[str]) -> str:
    if not items:
        return "<em>None</em>"
    return ", ".join(html.escape(i) for i in items)


def render_html_report(
    run_payload: dict[str, Any],
    delta_record: dict[str, Any],
    executive_brief: dict[str, Any],
) -> str:
    """Render must-ship HTML report sections as a self-contained page."""
    cities = run_payload.get("cities") or {}
    extremes = run_payload.get("extremes") or {}
    flags = run_payload.get("threshold_flags") or {}
    run_ts = _fmt(run_payload.get("run_timestamp"))
    mood = str(executive_brief.get("mood") or "notable").lower()
    theme = MOOD_THEME.get(mood, MOOD_THEME["notable"])

    city_cards: list[str] = []
    city_rows: list[str] = []
    for name in sorted(cities):
        entry = cities[name]
        daily = ((entry.get("forecast") or {}).get("daily") or {})
        aqi_raw = (entry.get("air_quality") or {}).get("us_aqi")
        max_t = _num((daily.get("temperature_2m_max") or [None])[0])
        min_t = _num((daily.get("temperature_2m_min") or [None])[0])
        gust = _num((daily.get("wind_gusts_10m_max") or [None])[0])
        precip = _num((daily.get("precipitation_sum") or [None])[0])
        code = (daily.get("weather_code") or [None])[0]
        icon, label = weather_icon(code)
        aqi = _num(aqi_raw)

        city_cards.append(
            f"""
            <article class="city-card">
              <div class="wx-icon" title="{html.escape(label)}">{icon}</div>
              <div class="city-meta">
                <h3>{_fmt(name)}</h3>
                <p class="wx-label">{html.escape(label)}</p>
                <p class="temps">
                  <span class="hi">{_temp_cell(max_t)}</span>
                  <span class="lo">{_temp_cell(min_t, cold=True)}</span>
                </p>
                <p class="metrics">💨 {_gust_badge(gust)} km/h · 💧 {_fmt(None if precip is None else f"{precip:.1f}")} mm</p>
                <p>{_aqi_badge(aqi)}</p>
              </div>
            </article>
            """
        )
        city_rows.append(
            "<tr>"
            f"<td><span class=\"wx-inline\">{icon}</span> {_fmt(name)}</td>"
            f"<td>{_temp_cell(max_t)}</td>"
            f"<td>{_temp_cell(min_t, cold=True)}</td>"
            f"<td>{_gust_badge(gust)}</td>"
            f"<td>{_fmt(None if precip is None else f'{precip:.1f}')}</td>"
            f"<td>{_aqi_badge(aqi)}</td>"
            "</tr>"
        )

    def extreme_card(label: str, key: str, icon: str) -> str:
        item = extremes.get(key)
        if not item:
            body = "—"
        elif "cities" in item:
            body = (
                f"{html.escape(', '.join(item.get('cities') or []))} "
                f"<strong>{_fmt(item.get('value'))}</strong>"
            )
        else:
            body = (
                f"{_fmt(item.get('city'))} "
                f"<strong>{_fmt(item.get('value'))}</strong>"
            )
        return (
            f'<div class="extreme-card"><div class="ex-icon">{icon}</div>'
            f"<div><div class=\"ex-label\">{label}</div>"
            f'<div class="ex-body">{body}</div></div></div>'
        )

    contrast = extremes.get("island_contrast") or {}
    north = contrast.get("north") or {}
    south = contrast.get("south") or {}

    def island_block(title: str, data: dict[str, Any], emoji: str) -> str:
        def v(key: str, suffix: str) -> str:
            num = _num(data.get(key))
            return "—" if num is None else f"{num:.1f}{suffix}"

        return f"""
        <div class="island-card">
          <h3>{emoji} {title}</h3>
          <ul>
            <li>Avg max: <strong>{v('avg_max_temp', '°C')}</strong></li>
            <li>Avg min: <strong>{v('avg_min_temp', '°C')}</strong></li>
            <li>Avg gust: <strong>{v('avg_max_gust', ' km/h')}</strong></li>
          </ul>
        </div>
        """

    watch_cities = flags.get("aqi_watch") or []
    unhealthy_cities = flags.get("aqi_unhealthy") or []
    if not watch_cities and not unhealthy_cities:
        aqi_section = (
            '<div class="status good-box">✅ All clear — no AQI watches</div>'
        )
    else:
        bits = []
        if watch_cities:
            bits.append(
                f'<div class="status warn-box">⚠️ Watch: '
                f"{_list_or_none(watch_cities)}</div>"
            )
        if unhealthy_cities:
            bits.append(
                f'<div class="status bad-box">🚨 Unhealthy: '
                f"{_list_or_none(unhealthy_cities)}</div>"
            )
        aqi_section = "".join(bits)

    if delta_record.get("is_first_run") or delta_record.get("comparison_unavailable"):
        delta_section = (
            f'<div class="status muted-box">{_fmt(delta_record.get("delta_note"))}</div>'
        )
    else:
        new_alerts = delta_record.get("new_alerts") or {}
        cleared = delta_record.get("cleared_alerts") or {}
        temp_changes = delta_record.get("significant_temp_changes") or []
        aqi_changes = delta_record.get("significant_aqi_changes") or []

        def alert_lines(bucket: dict[str, list[str]]) -> str:
            lines = []
            for key, values in bucket.items():
                if values:
                    lines.append(
                        f"<li><strong>{html.escape(key)}</strong>: "
                        f"{_list_or_none(values)}</li>"
                    )
            return "".join(lines) or "<li><em>None</em></li>"

        temp_html = "".join(
            f"<li>{_fmt(c.get('city'))}: {_fmt(c.get('previous'))} → "
            f"{_fmt(c.get('current'))} "
            f"(<span class=\"delta\">{_fmt(c.get('delta'))}°C</span>)</li>"
            for c in temp_changes
        ) or "<li><em>None</em></li>"
        aqi_html = "".join(
            f"<li>{_fmt(c.get('city'))}: {_fmt(c.get('previous'))} → "
            f"{_fmt(c.get('current'))} "
            f"(<span class=\"delta\">{_fmt(c.get('delta'))}</span>)</li>"
            for c in aqi_changes
        ) or "<li><em>None</em></li>"

        delta_section = f"""
        <div class="delta-grid">
          <div class="delta-card"><h3>🆕 New alerts</h3><ul>{alert_lines(new_alerts)}</ul></div>
          <div class="delta-card"><h3>✅ Cleared alerts</h3><ul>{alert_lines(cleared)}</ul></div>
          <div class="delta-card"><h3>🌡️ Temp swings</h3><ul>{temp_html}</ul></div>
          <div class="delta-card"><h3>💨 AQI swings</h3><ul>{aqi_html}</ul></div>
        </div>
        """

    bullets = "".join(
        f"<li>{_fmt(b)}</li>" for b in (executive_brief.get("bullets") or [])
    )
    watchouts = executive_brief.get("watchouts") or []
    watchout_html = (
        "".join(f'<li class="watch-item">⚠️ {_fmt(w)}</li>' for w in watchouts)
        if watchouts
        else '<li class="ok-item">✅ None</li>'
    )
    city_list = ", ".join(city.name for city in WATCHED_CITIES)
    first_code = None
    if cities:
        first_city = next(iter(cities.values()))
        codes = (
            ((first_city.get("forecast") or {}).get("daily") or {}).get("weather_code")
            or [None]
        )
        first_code = codes[0]
    hero_icon, _ = weather_icon(first_code)

    asset_base = report_link_base()
    favicon_href = favicon_data_uri()
    og_image = f"{asset_base}/og.jpg" if asset_base else ""
    og_url = f"{asset_base}/report" if asset_base else ""
    description = html.escape(
        str(executive_brief.get("headline") or "Daily NZ weather digest")
    )
    og_image_tags = (
        f'\n  <meta property="og:image" content="{html.escape(og_image)}"/>'
        f'\n  <meta property="og:image:type" content="image/jpeg"/>'
        f'\n  <meta property="og:image:width" content="1200"/>'
        f'\n  <meta property="og:image:height" content="630"/>'
        f'\n  <meta name="twitter:card" content="summary_large_image"/>'
        f'\n  <meta name="twitter:image" content="{html.escape(og_image)}"/>'
        if og_image
        else ""
    )
    og_url_tag = (
        f'\n  <meta property="og:url" content="{html.escape(og_url)}"/>'
        if og_url
        else ""
    )
    absolute_icon = (
        f'\n  <link rel="icon" href="{html.escape(asset_base)}/favicon.svg" '
        f'type="image/svg+xml"/>'
        f'\n  <link rel="apple-touch-icon" href="{html.escape(asset_base)}/favicon.png"/>'
        if asset_base
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Weather Pulse NZ</title>
  <meta name="description" content="{description}"/>
  <meta property="og:site_name" content="Weather Pulse NZ"/>
  <meta property="og:title" content="Weather Pulse NZ"/>
  <meta property="og:description" content="{description}"/>
  <meta property="og:type" content="website"/>{og_url_tag}{og_image_tags}
  <link rel="icon" href="{favicon_href}" type="image/svg+xml"/>{absolute_icon}
  <style>
    :root {{
      --accent: {theme['accent']};
      --accent-bg: {theme['bg']};
      --ink: #143247;
      --muted: #5b7386;
      --card: #ffffff;
      --line: #d7e3ee;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
      background:
        radial-gradient(1200px 500px at 10% -10%, var(--accent-bg), transparent 60%),
        radial-gradient(900px 400px at 100% 0%, #dff3ff, transparent 55%),
        linear-gradient(180deg, #f4f8fb 0%, #eef3f7 100%);
    }}
    .wrap {{ max-width: 1080px; margin: 0 auto; padding: 1.5rem; }}
    .hero {{
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 1rem;
      align-items: center;
      background: linear-gradient(135deg, #0b3d5c, #1a6b8a 55%, var(--accent));
      color: #fff;
      border-radius: 20px;
      padding: 1.4rem 1.6rem;
      box-shadow: 0 16px 40px rgba(11, 61, 92, 0.25);
    }}
    .hero-emoji {{ font-size: 3.2rem; filter: drop-shadow(0 4px 8px rgba(0,0,0,.2)); }}
    .hero h1 {{ margin: 0 0 .35rem; font-size: 1.7rem; }}
    .hero p {{ margin: 0; opacity: .92; }}
    .mood-pill {{
      display: inline-block;
      margin-top: .7rem;
      padding: .25rem .7rem;
      border-radius: 999px;
      background: rgba(255,255,255,.2);
      border: 1px solid rgba(255,255,255,.35);
      font-weight: 700;
      letter-spacing: .02em;
    }}
    section {{
      margin-top: 1.25rem;
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 1.1rem 1.2rem;
      box-shadow: 0 8px 24px rgba(20, 50, 71, 0.06);
    }}
    section h1 {{
      margin: 0 0 .8rem;
      font-size: 1.2rem;
      color: #0b3d5c;
      border-left: 4px solid var(--accent);
      padding-left: .6rem;
    }}
    .headline {{
      font-size: 1.25rem;
      font-weight: 700;
      color: #0b3d5c;
      margin: .2rem 0 .8rem;
    }}
    ul {{ margin: .4rem 0 0; padding-left: 1.1rem; }}
    li {{ margin: .25rem 0; }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
      gap: .8rem;
    }}
    .city-card {{
      display: grid;
      grid-template-columns: auto 1fr;
      gap: .65rem;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: .75rem;
      background: linear-gradient(180deg, #fff, #f7fbfe);
    }}
    .wx-icon {{ font-size: 2.2rem; line-height: 1; }}
    .wx-inline {{ font-size: 1.1rem; }}
    .city-meta h3 {{ margin: 0; font-size: 1rem; }}
    .wx-label {{ margin: .1rem 0 .35rem; color: var(--muted); font-size: .85rem; }}
    .temps {{ margin: 0; font-size: 1.05rem; }}
    .temps .hi {{ color: #d35400; font-weight: 700; margin-right: .45rem; }}
    .temps .hi::after {{ content: "° max"; font-weight: 500; font-size: .75rem; color: var(--muted); margin-left: .15rem; }}
    .temps .lo {{ color: #2471a3; font-weight: 700; }}
    .temps .lo::after {{ content: "° min"; font-weight: 500; font-size: .75rem; color: var(--muted); margin-left: .15rem; }}
    .metrics {{ margin: .35rem 0; color: var(--muted); font-size: .86rem; }}
    .badge {{
      display: inline-block;
      padding: .12rem .45rem;
      border-radius: 999px;
      font-size: .78rem;
      font-weight: 700;
    }}
    .badge.good {{ background: #d5f5e3; color: #1a7f4b; }}
    .badge.ok {{ background: #fdebd0; color: #9a5b00; }}
    .badge.warn {{ background: #fdebd0; color: #9a5b00; }}
    .badge.bad {{ background: #fadbd8; color: #922b21; }}
    .badge.muted {{ background: #eaecee; color: #566573; }}
    .temp-hot {{ color: #d35400; font-weight: 700; }}
    .temp-cold {{ color: #1a5276; font-weight: 700; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: .6rem; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: .55rem .45rem; text-align: left; }}
    th {{ background: #eef5fa; color: #0b3d5c; font-size: .85rem; }}
    .extremes {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: .7rem;
    }}
    .extreme-card {{
      display: flex; gap: .6rem; align-items: flex-start;
      background: var(--accent-bg);
      border: 1px solid color-mix(in srgb, var(--accent) 35%, white);
      border-radius: 12px; padding: .7rem;
    }}
    .ex-icon {{ font-size: 1.5rem; }}
    .ex-label {{ font-size: .78rem; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }}
    .ex-body {{ margin-top: .15rem; }}
    .island-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: .8rem; margin-top: .8rem; }}
    .island-card {{
      border-radius: 12px; padding: .8rem 1rem;
      background: linear-gradient(160deg, #eaf6ff, #fff);
      border: 1px solid var(--line);
    }}
    .island-card h3 {{ margin: 0 0 .4rem; font-size: 1rem; }}
    .status {{ border-radius: 12px; padding: .8rem 1rem; font-weight: 600; }}
    .good-box {{ background: #d5f5e3; color: #1a7f4b; }}
    .warn-box {{ background: #fdebd0; color: #9a5b00; margin-bottom: .5rem; }}
    .bad-box {{ background: #fadbd8; color: #922b21; }}
    .muted-box {{ background: #eaecee; color: #566573; }}
    .delta-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: .7rem;
    }}
    .delta-card {{
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: .7rem .85rem;
      background: #fbfcfd;
    }}
    .delta-card h3 {{ margin: 0 0 .4rem; font-size: .95rem; }}
    .delta {{ font-weight: 700; color: var(--accent); }}
    .watch-item {{ color: #9a5b00; }}
    .ok-item {{ color: #1a7f4b; }}
    footer.sources {{ color: var(--muted); font-size: .9rem; }}
    @media (max-width: 700px) {{
      .hero {{ grid-template-columns: 1fr; }}
      .island-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header class="hero">
      <div class="hero-emoji">{hero_icon}</div>
      <div>
        <h1>Weather Pulse NZ</h1>
        <p>Daily briefing · {_fmt(run_payload.get('run_timestamp'))}</p>
        <span class="mood-pill">Mood: {html.escape(theme['label'])}</span>
      </div>
    </header>

    <section id="executive-brief">
      <h1>Executive Brief</h1>
      <p class="headline">{_fmt(executive_brief.get('headline'))}</p>
      <ul>{bullets}</ul>
      <h3>Watchouts</h3>
      <ul>{watchout_html}</ul>
    </section>

    <section id="city-snapshot-board">
      <h1>City Snapshot Board</h1>
      <div class="cards">
        {''.join(city_cards)}
      </div>
      <table>
        <thead>
          <tr><th>City</th><th>Max °C</th><th>Min °C</th><th>Gust km/h</th><th>Precip mm</th><th>US AQI</th></tr>
        </thead>
        <tbody>
          {''.join(city_rows)}
        </tbody>
      </table>
    </section>

    <section id="nz-extremes">
      <h1>NZ Extremes</h1>
      <div class="extremes">
        {extreme_card('Hottest', 'hottest', '🔥')}
        {extreme_card('Coldest', 'coldest', '🧊')}
        {extreme_card('Windiest', 'windiest', '💨')}
        {extreme_card('Wettest', 'wettest', '💧')}
        {extreme_card('Largest swing', 'largest_swing', '↕️')}
      </div>
      <div class="island-grid">
        {island_block('North Island', north, '🗺️')}
        {island_block('South Island', south, '🏔️')}
      </div>
    </section>

    <section id="air-quality-watch">
      <h1>Air Quality Watch</h1>
      {aqi_section}
    </section>

    <section id="delta-vs-last-run">
      <h1>Delta vs Last Run</h1>
      {delta_section}
    </section>

    <section id="sources-and-attribution" class="sources">
      <h1>Sources and Attribution</h1>
      <p>Data: Open-Meteo (CC BY 4.0)</p>
      <p>Run timestamp: {run_ts}</p>
      <p>Cities: {html.escape(city_list)}</p>
      <p>Report object: <code>{html.escape(HTML_REPORT_KEY)}</code></p>
    </section>
  </div>
</body>
</html>
"""


def write_raw_json(run_payload: dict[str, Any], run_timestamp: datetime) -> bool:
    """Write full Run_Payload JSON archive to S3."""
    key = _utc_raw_key(run_timestamp)
    try:
        client = boto3.client("s3", region_name=AWS_REGION)
        client.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=json.dumps(run_payload, default=str).encode("utf-8"),
            ContentType="application/json",
        )
        return True
    except (BotoCoreError, ClientError, TypeError) as exc:
        logger.error("S3 raw JSON write failed: %s", exc)
        return False


def write_html_report(
    run_payload: dict[str, Any],
    delta_record: dict[str, Any],
    executive_brief: dict[str, Any],
) -> bool:
    """Write latest HTML report to S3."""
    try:
        client = boto3.client("s3", region_name=AWS_REGION)
        body = render_html_report(run_payload, delta_record, executive_brief)
        client.put_object(
            Bucket=S3_BUCKET,
            Key=HTML_REPORT_KEY,
            Body=body.encode("utf-8"),
            ContentType="text/html",
        )
        return True
    except (BotoCoreError, ClientError, TypeError) as exc:
        logger.error("S3 HTML report write failed: %s", exc)
        return False
