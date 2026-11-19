from __future__ import annotations

from datetime import datetime, timedelta
from xml.sax.saxutils import escape

from greenwindow.forecast import Forecast

BLOCKS = " ▁▂▃▄▅▆▇█"


def sparkline(values: list[float]) -> str:
    low, high = min(values), max(values)
    span = (high - low) or 1.0
    return "".join(BLOCKS[1 + int((v - low) / span * (len(BLOCKS) - 2))] for v in values)


def text_chart(
    forecast: Forecast,
    start: datetime,
    end: datetime,
    window: tuple[datetime, datetime] | None,
) -> str:
    points = [p for p in forecast.points if start - forecast.step < p.start < end]
    low = min(p.intensity for p in points)
    high = max(p.intensity for p in points)
    width = 36
    lines = []
    for point in points:
        filled = 4 + int((point.intensity - low) / ((high - low) or 1) * (width - 4))
        in_window = (
            window is not None
            and point.start < window[1]
            and point.start + forecast.step > window[0]
        )
        bar = ("█" if in_window else "░") * filled
        marker = "  ◀ run" if in_window else ""
        lines.append(f"{point.start:%a %H:%M}Z  {point.intensity:6.0f}  {bar}{marker}")
    return "\n".join(lines)


def svg_chart(
    forecast: Forecast,
    start: datetime,
    end: datetime,
    window: tuple[datetime, datetime] | None,
    now: datetime,
    title: str,
) -> str:
    width, height = 900, 340
    left, right, top, bottom = 64, 24, 56, 48
    points = [p for p in forecast.points if start - forecast.step < p.start < end]
    values = [p.intensity for p in points]
    low = min(values) // 50 * 50
    high = -(-max(values) // 50) * 50
    span_t = (end - start).total_seconds()

    def x(moment: datetime) -> float:
        offset = (min(max(moment, start), end) - start).total_seconds()
        return left + offset / span_t * (width - left - right)

    def y(value: float) -> float:
        return top + (high - value) / ((high - low) or 1) * (height - top - bottom)

    path = []
    for point in points:
        path.append(f"{x(point.start):.1f},{y(point.intensity):.1f}")
        path.append(f"{x(point.start + forecast.step):.1f},{y(point.intensity):.1f}")
    area = f"{x(start):.1f},{y(low):.1f} " + " ".join(path) + f" {x(end):.1f},{y(low):.1f}"

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="12">',
        '<rect width="100%" height="100%" rx="12" fill="#0d1117"/>',
        f'<text x="{left}" y="30" fill="#e6edf3" font-size="16" font-weight="600">'
        f"{escape(title)}</text>",
    ]
    for tick in range(int(low), int(high) + 1, 50):
        parts.append(
            f'<line x1="{left}" x2="{width - right}" y1="{y(tick):.1f}" y2="{y(tick):.1f}" '
            f'stroke="#30363d" stroke-width="1"/>'
            f'<text x="{left - 8}" y="{y(tick) + 4:.1f}" fill="#8b949e" text-anchor="end">'
            f"{tick}</text>"
        )
    tick_time = start.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    while tick_time < end:
        if tick_time.hour % 3 == 0:
            parts.append(
                f'<text x="{x(tick_time):.1f}" y="{height - bottom + 18}" fill="#8b949e" '
                f'text-anchor="middle">{tick_time:%H:%M}</text>'
            )
        tick_time += timedelta(hours=1)
    if window:
        x1, x2 = x(window[0]), x(window[1])
        parts.append(
            f'<rect x="{x1:.1f}" y="{top}" width="{x2 - x1:.1f}" height="{height - top - bottom}" '
            f'fill="#2ea043" fill-opacity="0.25" stroke="#2ea043"/>'
            f'<text x="{(x1 + x2) / 2:.1f}" y="{top - 8}" fill="#3fb950" text-anchor="middle" '
            f'font-weight="600">greenest window</text>'
        )
    parts.append(
        f'<polygon points="{area}" fill="#d29922" fill-opacity="0.12"/>'
        f'<polyline points="{" ".join(path)}" fill="none" stroke="#d29922" stroke-width="2"/>'
        f'<line x1="{x(now):.1f}" x2="{x(now):.1f}" y1="{top}" y2="{height - bottom}" '
        f'stroke="#58a6ff" stroke-dasharray="4 4"/>'
        f'<text x="{x(now) + 4:.1f}" y="{height - bottom - 6}" fill="#58a6ff">now</text>'
        f'<text x="14" y="{(top + height - bottom) / 2:.1f}" fill="#8b949e" '
        f'transform="rotate(-90 14 {(top + height - bottom) / 2:.1f})" text-anchor="middle">'
        f"gCO2eq/kWh</text>"
        f'<text x="{width - right}" y="{height - 10}" fill="#8b949e" text-anchor="end">'
        f"UTC · source: {escape(forecast.source)}</text>",
    )
    parts.append("</svg>")
    return "\n".join(parts)
