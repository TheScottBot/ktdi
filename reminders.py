"""Campaign reminder schedules: parse "mondays at 1800" and work out when a reminder is next due."""

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_WORDS = {
    "monday": [0], "mon": [0],
    "tuesday": [1], "tue": [1], "tues": [1],
    "wednesday": [2], "wed": [2], "weds": [2],
    "thursday": [3], "thu": [3], "thur": [3], "thurs": [3],
    "friday": [4], "fri": [4],
    "saturday": [5], "sat": [5],
    "sunday": [6], "sun": [6],
    "weekday": [0, 1, 2, 3, 4],
    "weekend": [5, 6],
    "day": [0, 1, 2, 3, 4, 5, 6], "daily": [0, 1, 2, 3, 4, 5, 6], "everyday": [0, 1, 2, 3, 4, 5, 6],
}
FILLER_WORDS = {"every", "each", "on", "and", "at", "the", "a", "week", "weeks", "night", "nights", "evening", "evenings"}
FORTNIGHTLY_RE = re.compile(r"\b(every other|every second|every 2|every two|fortnightly|biweekly|bi-weekly)\b")
TIME_RE = re.compile(r"(?:\bat\s+)?\b(\d{1,2})(?:[:.]?(\d{2}))?\s*(am|pm)?\s*$")

EXAMPLES = "`mondays at 1800`, `monday 6pm`, `mondays and thursdays at 19:30`, `every other friday at 7pm`"


class ScheduleError(ValueError):
    """Couldn't understand the schedule. The message is safe to show users."""


@dataclass(frozen=True)
class Schedule:
    days: tuple[int, ...]  # 0 = Monday
    hour: int
    minute: int
    every_weeks: int = 1  # 2 = fortnightly

    def describe(self) -> str:
        """e.g. 'Mondays and Thursdays at 18:00' or 'Every other Friday at 19:30'."""
        clock = f"{self.hour:02d}:{self.minute:02d}"
        if len(self.days) == 7:
            days = "Every day"
        elif self.days == (0, 1, 2, 3, 4):
            days = "Weekdays"
        elif self.days == (5, 6):
            days = "Weekends"
        else:
            names = [DAY_NAMES[d] + ("" if self.every_weeks > 1 else "s") for d in self.days]
            days = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        if self.every_weeks > 1:
            if days in ("Every day", "Weekdays", "Weekends"):
                return f"{days} every other week at {clock}"
            return f"Every other {days} at {clock}"
        return f"{days} at {clock}"

    def to_storage(self) -> tuple[str, str, int]:
        return ",".join(map(str, self.days)), f"{self.hour:02d}:{self.minute:02d}", self.every_weeks

    @classmethod
    def from_storage(cls, days: str, clock: str, every_weeks: int) -> "Schedule":
        hour, minute = map(int, clock.split(":"))
        return cls(tuple(int(d) for d in days.split(",")), hour, minute, every_weeks)


def parse_schedule(text: str) -> Schedule:
    lowered = " ".join(text.lower().replace(",", " ").split())
    every_weeks = 2 if FORTNIGHTLY_RE.search(lowered) else 1
    lowered = FORTNIGHTLY_RE.sub(" ", lowered).strip()

    match = TIME_RE.search(lowered)
    if not match:
        raise ScheduleError(f"Add a time at the end, e.g. {EXAMPLES}.")
    hour, minute, meridiem = int(match.group(1)), int(match.group(2) or 0), match.group(3)
    if meridiem:
        if not 1 <= hour <= 12:
            raise ScheduleError(f"{hour}{meridiem} isn't a time.")
        hour = hour % 12 + (12 if meridiem == "pm" else 0)
    if hour > 23 or minute > 59:
        raise ScheduleError(f"{hour:02d}:{minute:02d} isn't a valid time. Use 24-hour time like 1800, or 6pm.")

    days: set[int] = set()
    for word in re.findall(r"[a-z]+", lowered[:match.start()]):
        if word in FILLER_WORDS:
            continue
        singular = word[:-1] if word.endswith("s") and word[:-1] in DAY_WORDS else word
        if singular not in DAY_WORDS:
            raise ScheduleError(f"I don't know the day `{word}`. Try something like {EXAMPLES}.")
        days.update(DAY_WORDS[singular])
    if not days:
        raise ScheduleError(f"Which day? Try something like {EXAMPLES}.")
    return Schedule(tuple(sorted(days)), hour, minute, every_weeks)


LEAD_MAX_MINUTES = 48 * 60
LEAD_UNITS = r"(m|mins?|minutes?|h|hrs?|hours?|d|days?)"
LEAD_UNIT_MINUTES = {"m": 1, "h": 60, "d": 24 * 60}
LEAD_RE = re.compile(
    r"[,\s]*(?:and\s+)?(?:(?:remind(?:\s+(?:me|us))?|ping|warn(?:ing)?)\s+)?"
    rf"((?:\d+\s*{LEAD_UNITS}\s*(?:and\s+)?)+|half an hour|an hour|a half hour|a day)\s+(?:before|early|beforehand|ahead)\b",
    re.IGNORECASE,
)


def split_lead(text: str) -> tuple[str, int | None]:
    """'mondays at 1900, 15 minutes before' -> ('mondays at 1900', 15). None if no warning was given."""
    match = LEAD_RE.search(text)
    if not match:
        return text, None
    amount = match.group(1).lower()
    if amount in ("half an hour", "a half hour"):
        minutes = 30
    elif amount == "an hour":
        minutes = 60
    elif amount == "a day":
        minutes = 24 * 60
    else:
        minutes = sum(int(n) * LEAD_UNIT_MINUTES[unit[0].lower()]
                      for n, unit in re.findall(rf"(\d+)\s*{LEAD_UNITS}", amount, re.IGNORECASE))
    if minutes > LEAD_MAX_MINUTES:
        raise ScheduleError(f"That's a long warning. The most is {LEAD_MAX_MINUTES // 60} hours before.")
    return (text[:match.start()] + " " + text[match.end():]).strip(), minutes


def describe_lead(minutes: int) -> str:
    """15 -> '15 minutes before', 90 -> '1 hour 30 minutes before', 0 -> 'at the start time'."""
    if minutes <= 0:
        return "at the start time"
    if minutes % (24 * 60) == 0:
        days = minutes // (24 * 60)
        return f"{days} day{'s' if days != 1 else ''} before"
    hours, mins = divmod(minutes, 60)
    parts = ([f"{hours} hour{'s' if hours != 1 else ''}"] if hours else []) + \
            ([f"{mins} minute{'s' if mins != 1 else ''}"] if mins else [])
    return " ".join(parts) + " before"


MONTHS = {name: number for number, names in enumerate(
    [("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",), ("jun", "june"),
     ("jul", "july"), ("aug", "august"), ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"),
     ("dec", "december")], start=1) for name in names}
START_RE = re.compile(r"\s+(?:from|starting(?:\s+from|\s+on)?)\s+(.+)$", re.IGNORECASE)
DATE_EXAMPLES = "`19 oct`, `oct 19`, `19/10`, `2026-10-19`, `tomorrow`"


def split_start(text: str) -> tuple[str, str | None]:
    """'every other monday at 7pm from 19 oct' -> ('every other monday at 7pm', '19 oct')."""
    match = START_RE.search(text)
    return (text[:match.start()], match.group(1)) if match else (text, None)


def parse_date(text: str, today: date) -> date:
    """UK-style dates. A date without a year means the next time that date comes round."""
    cleaned = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text.strip().lower().replace(",", " "))
    if cleaned in ("today", "tonight"):
        return today
    if cleaned == "tomorrow":
        return today + timedelta(days=1)

    year = None
    if match := re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", cleaned):
        year, month, day = map(int, match.groups())
    elif match := re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?", cleaned):
        day, month = int(match.group(1)), int(match.group(2))
        year = int(match.group(3)) if match.group(3) else None
    elif match := re.fullmatch(r"(\d{1,2})\s+([a-z]+)(?:\s+(\d{4}))?", cleaned):
        day, month = int(match.group(1)), MONTHS.get(match.group(2))
        year = int(match.group(3)) if match.group(3) else None
    elif match := re.fullmatch(r"([a-z]+)\s+(\d{1,2})(?:\s+(\d{4}))?", cleaned):
        month, day = MONTHS.get(match.group(1)), int(match.group(2))
        year = int(match.group(3)) if match.group(3) else None
    else:
        raise ScheduleError(f"I couldn't read the date `{text}`. Try {DATE_EXAMPLES}.")
    if not month:
        raise ScheduleError(f"I couldn't read the date `{text}`. Try {DATE_EXAMPLES}.")
    if year is not None and year < 100:
        year += 2000
    try:
        result = date(year or today.year, month, day)
    except ValueError:
        raise ScheduleError(f"`{text}` isn't a real date.") from None
    if year is None and result < today:
        result = date(today.year + 1, month, day)  # "5 jan" in December means next January.
    if result < today:
        raise ScheduleError(f"{result:%d %b %Y} is in the past.")
    return result


def first_on_or_after(schedule: "Schedule", start: date, now: datetime, tz: ZoneInfo) -> tuple[datetime, date]:
    """The first reminder on or after `start` (and after now), plus the anchor date for fortnightly schedules.

    The week containing `start` counts as an "on" week, so "every other monday from 19 oct" goes 19 Oct, 2 Nov, ...
    """
    start_of_day = datetime.combine(start, time.min, tzinfo=tz) - timedelta(seconds=1)
    after = max(start_of_day, now.astimezone(tz))
    first = next_occurrence(schedule, after, tz, anchor=start)
    return first, start


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def next_occurrence(schedule: Schedule, after: datetime, tz: ZoneInfo, anchor: date | None = None) -> datetime:
    """The next time (UTC) strictly after `after` that the reminder is due.

    For fortnightly schedules, `anchor` is a date in one of the "on" weeks.
    Times are local to `tz`, so summer time is handled.
    """
    local_after = after.astimezone(tz)
    for offset in range(0, 7 * schedule.every_weeks + 8):
        day = local_after.date() + timedelta(days=offset)
        if day.weekday() not in schedule.days:
            continue
        if schedule.every_weeks > 1 and anchor is not None:
            weeks_apart = (_week_start(day) - _week_start(anchor)).days // 7
            if weeks_apart % schedule.every_weeks:
                continue
        candidate = datetime.combine(day, time(schedule.hour, schedule.minute), tzinfo=tz)
        if candidate > local_after:
            return candidate.astimezone(timezone.utc)
    raise RuntimeError("No upcoming occurrence found")  # Can't happen with at least one day.
