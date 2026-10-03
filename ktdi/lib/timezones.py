"""Timezones and times as people type them: "london", "New York", "EST", "UTC+5:30", "Europe/Paris"; "7pm", "19:00".

No Discord code. Zones come from the IANA database (the tzdata package on Windows), so summer time is handled.
"""

import re
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from functools import cache
from zoneinfo import ZoneInfo, available_timezones


class TimezoneError(ValueError):
    """Something we couldn't understand; the message is shown to the user."""


# Abbreviations and nicknames, mapped to a place so summer time comes out right: "EST" in July still means New
# York time, and "GMT" in summer means UK time, the way people use them.
ALIASES = {
    "utc": "UTC", "z": "UTC", "zulu": "UTC",
    "gmt": "Europe/London", "bst": "Europe/London", "uk": "Europe/London", "british": "Europe/London",
    "est": "America/New_York", "edt": "America/New_York", "et": "America/New_York", "eastern": "America/New_York",
    "cst": "America/Chicago", "cdt": "America/Chicago", "ct": "America/Chicago", "central": "America/Chicago",
    "mst": "America/Denver", "mdt": "America/Denver", "mt": "America/Denver", "mountain": "America/Denver",
    "pst": "America/Los_Angeles", "pdt": "America/Los_Angeles", "pt": "America/Los_Angeles",
    "pacific": "America/Los_Angeles",
    "akst": "America/Anchorage", "akdt": "America/Anchorage", "hst": "Pacific/Honolulu",
    "cet": "Europe/Paris", "cest": "Europe/Paris", "eet": "Europe/Athens", "eest": "Europe/Athens",
    "ist": "Asia/Kolkata", "india": "Asia/Kolkata", "jst": "Asia/Tokyo", "kst": "Asia/Seoul",
    "sgt": "Asia/Singapore", "hkt": "Asia/Hong_Kong",
    "aest": "Australia/Sydney", "aedt": "Australia/Sydney", "awst": "Australia/Perth",
    "nzst": "Pacific/Auckland", "nzdt": "Pacific/Auckland",
}
OFFSET_RE = re.compile(r"^(?:utc|gmt)?\s*([+-])\s*(\d{1,2})(?:[:.]?(\d{2}))?$")
CLOCK_RE = re.compile(r"^(\d{1,2})(?:[:.]?(\d{2}))?\s*(am|pm)?$")
ZONE_EXAMPLES = "a city (`London`, `New York`), an abbreviation (`EST`, `BST`) or an offset (`UTC+2`)"
TIME_EXAMPLES = "`7pm`, `19:00`, `1930`, `noon` or `now`"


def _normal(text: str) -> str:
    return " ".join(text.replace("_", " ").split()).casefold()


def place(key: str) -> str:
    """Europe/London -> London, America/Argentina/Buenos_Aires -> Buenos Aires."""
    return key.split("/")[-1].replace("_", " ")


@cache
def _zone_index() -> tuple[dict[str, str], dict[str, str]]:
    """Every zone by full name, and by its place name (the first in alphabetical order wins a clash)."""
    names, places = {}, {}
    for key in sorted(available_timezones()):
        names[_normal(key)] = key
        if "/" in key and not key.startswith(("Etc/", "SystemV/")):
            places.setdefault(_normal(place(key)), key)
    return names, places


def parse_zone(text: str) -> tzinfo:
    wanted = _normal(text)
    if not wanted:
        raise TimezoneError(f"Which timezone? Try {ZONE_EXAMPLES}.")
    if wanted in ALIASES:
        return ZoneInfo(ALIASES[wanted])
    if match := OFFSET_RE.match(wanted):
        sign, hours, minutes = match.group(1), int(match.group(2)), int(match.group(3) or 0)
        if hours > 14 or minutes > 59:
            raise TimezoneError(f"`{text}` is further from UTC than anywhere on Earth.")
        offset = timedelta(hours=hours, minutes=minutes) * (-1 if sign == "-" else 1)
        return timezone(offset, f"UTC{sign}{hours}" + (f":{minutes:02d}" if minutes else ""))
    names, places = _zone_index()
    key = names.get(wanted) or places.get(wanted)
    if key is None:
        raise TimezoneError(f"I don't know the timezone `{text}`. Try {ZONE_EXAMPLES}.")
    return ZoneInfo(key)


def zone_id(tz: tzinfo) -> str:
    """How a zone is stored. parse_zone(zone_id(tz)) gives the same zone back."""
    return tz.key if isinstance(tz, ZoneInfo) else tz.tzname(None)


def describe_zone(tz: tzinfo, at: datetime) -> str:
    """For people: "London (BST)", "New York (EDT)", "UTC", "UTC+5:30"."""
    if not isinstance(tz, ZoneInfo):
        return tz.tzname(None)
    if tz.key == "UTC":
        return "UTC"
    abbreviation = at.astimezone(tz).tzname()
    if abbreviation[0] in "+-":  # Some places have no letters, just an offset like "+03".
        abbreviation = f"UTC{abbreviation}"
    return f"{place(tz.key)} ({abbreviation})"


def parse_clock(text: str) -> time | None:
    """A time of day, or None for "now"."""
    wanted = _normal(text)
    if wanted in ("now", "right now"):
        return None
    if wanted == "noon" or wanted == "midday":
        return time(12, 0)
    if wanted == "midnight":
        return time(0, 0)
    match = CLOCK_RE.match(wanted)
    if not match:
        raise TimezoneError(f"I don't understand the time `{text}`. Try {TIME_EXAMPLES}.")
    hour, minute, meridiem = int(match.group(1)), int(match.group(2) or 0), match.group(3)
    if meridiem:
        if not 1 <= hour <= 12:
            raise TimezoneError(f"`{text}` isn't a time.")
        hour = hour % 12 + (12 if meridiem == "pm" else 0)
    if hour > 23 or minute > 59:
        raise TimezoneError(f"`{text}` isn't a time. Try {TIME_EXAMPLES}.")
    return time(hour, minute)


def convert(clock: time | None, from_tz: tzinfo, to_tz: tzinfo, now: datetime) -> tuple[datetime, datetime]:
    """That time today where it's from (or now), and the same moment where it's going."""
    if clock is None:
        start = now.astimezone(from_tz)
    else:
        today: date = now.astimezone(from_tz).date()
        start = datetime.combine(today, clock, tzinfo=from_tz)
    return start, start.astimezone(to_tz)


def day_note(start: datetime, end: datetime) -> str:
    days = (end.date() - start.date()).days
    return {1: " (the next day)", -1: " (the day before)"}.get(days, "")


def suggestions(typed: str, limit: int = 25) -> list[tuple[str, str]]:
    """(label, zone) pairs for autocomplete: abbreviations first, then places, then full names."""
    wanted = _normal(typed)
    found: list[tuple[str, str]] = []
    if wanted in ALIASES:
        found.append((f"{typed.upper()} ({ALIASES[wanted]})", ALIASES[wanted]))
    names, places = _zone_index()
    for name, key in places.items():
        if wanted in name and len(found) < limit:
            found.append((f"{place(key)} ({key})", key))
    for name, key in names.items():
        if wanted in name and len(found) < limit and all(key != f[1] for f in found):
            found.append((key, key))
    return found[:limit]
