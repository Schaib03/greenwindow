import re
from datetime import timedelta

_PART = re.compile(r"(\d+)([dhms])")
_UNITS = {"d": "days", "h": "hours", "m": "minutes", "s": "seconds"}


def parse_duration(text: str) -> timedelta:
    """Parse "90m", "1h30m", "2d"."""
    text = text.strip().lower()
    if not text or _PART.sub("", text):
        raise ValueError(f"invalid duration: {text!r}")
    parts = {_UNITS[unit]: int(value) for value, unit in _PART.findall(text)}
    duration = timedelta(**parts)
    if duration <= timedelta(0):
        raise ValueError(f"duration must be positive: {text!r}")
    return duration


def format_duration(delta: timedelta) -> str:
    seconds = int(delta.total_seconds())
    hours, rest = divmod(seconds, 3600)
    minutes = rest // 60
    if hours and minutes:
        return f"{hours}h{minutes:02d}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"
