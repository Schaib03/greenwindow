from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from greenwindow import providers
from greenwindow.chart import sparkline, svg_chart, text_chart
from greenwindow.durations import format_duration, parse_duration
from greenwindow.scheduler import energy_kwh, plan


def _forecast(args):
    provider = providers.from_env()
    return provider.forecast(args.zone)


def cmd_forecast(args) -> int:
    forecast = _forecast(args)
    now = datetime.now(UTC)
    end = min(now + parse_duration(args.horizon), forecast.end)
    values = [p.intensity for p in forecast.points if now - forecast.step < p.start < end]
    print(f"{forecast.zone}  {forecast.source}  {format_duration(end - now)} ahead")
    print(f"{sparkline(values)}  {min(values):.0f}–{max(values):.0f} gCO2eq/kWh")
    print()
    print(text_chart(forecast, now, end, None))
    return 0


def cmd_plan(args) -> int:
    forecast = _forecast(args)
    now = datetime.now(UTC)
    duration = parse_duration(args.duration)
    deadline = now + parse_duration(args.deadline)
    result = plan(forecast, now, duration, deadline, args.max_intensity)
    window = (result.start, result.start + duration)

    end = min(max(deadline, window[1]), forecast.end)
    print(text_chart(forecast, now, end, window))
    print()
    wait = result.start - now
    if result.delayed:
        grams = result.avoided_grams(energy_kwh(args.power_watts, duration))
        drop = (1 - result.intensity / result.intensity_now) * 100
        print(f"Start at {result.start:%a %H:%M} UTC (in {format_duration(wait)})")
        print(
            f"  {result.intensity_now:.0f} → {result.intensity:.0f} gCO2eq/kWh "
            f"(-{drop:.0f}%), about {grams:.0f} g CO2 avoided at {args.power_watts:.0f} W"
        )
    else:
        print(f"Start now ({result.reason}): {result.intensity_now:.0f} gCO2eq/kWh")

    if args.svg:
        title = (
            f"{forecast.zone} grid carbon intensity — best {format_duration(duration)} window "
            f"before {deadline:%a %H:%M} UTC"
        )
        chart_start = now - timedelta(hours=1)
        Path(args.svg).write_text(
            svg_chart(forecast, chart_start, end, window, now, title), encoding="utf-8"
        )
        print(f"Chart written to {args.svg}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="greenwindow",
        description="Find the greenest time to run a batch job. "
        "The provider is chosen with GREENWINDOW_PROVIDER (openmeteo, electricitymaps, static).",
    )
    parser.add_argument("--zone", default="MA", help="grid zone (default: MA)")
    sub = parser.add_subparsers(dest="command", required=True)

    forecast = sub.add_parser("forecast", help="show the carbon intensity forecast")
    forecast.add_argument("--horizon", default="24h")
    forecast.set_defaults(func=cmd_forecast)

    plan_cmd = sub.add_parser("plan", help="choose a start time for a job")
    plan_cmd.add_argument("--duration", required=True, help="expected run time, e.g. 45m")
    plan_cmd.add_argument("--deadline", required=True, help="must finish within, e.g. 12h")
    plan_cmd.add_argument("--power-watts", type=float, default=100)
    plan_cmd.add_argument("--max-intensity", type=float, default=None)
    plan_cmd.add_argument("--svg", help="also write the chart as SVG")
    plan_cmd.set_defaults(func=cmd_plan)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (providers.ProviderError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
