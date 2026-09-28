"""Reminder schedule parsing and date maths (ktdi.lib.reminders)."""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from ktdi.lib import reminders as r

UK = ZoneInfo("Europe/London")


@pytest.mark.parametrize("text, described", [
    ("mondays at 1800", "Mondays at 18:00"),
    ("Monday 6pm", "Mondays at 18:00"),
    ("mon 1830", "Mondays at 18:30"),
    ("mondays and thursdays at 7pm", "Mondays and Thursdays at 19:00"),
    ("tues, thurs 930pm", "Tuesdays and Thursdays at 21:30"),
    ("every other friday at 7:30pm", "Every other Friday at 19:30"),
    ("fortnightly on saturdays 14:00", "Every other Saturday at 14:00"),
    ("weekdays 9am", "Weekdays at 09:00"),
    ("weekends at 10.30", "Weekends at 10:30"),
    ("every day at 20:00", "Every day at 20:00"),
])
def test_parse_schedule(text, described):
    assert r.parse_schedule(text).describe() == described


@pytest.mark.parametrize("text, message", [
    ("mondays", "Add a time"),
    ("blursday at 6pm", "I don't know the day `blursday`"),
    ("monday at 25:00", "25:00 isn't a valid time"),
    ("monday 13pm", "13pm isn't a time"),
    ("at 6pm", "Which day?"),
])
def test_parse_schedule_errors(text, message):
    with pytest.raises(r.ScheduleError, match=message):
        r.parse_schedule(text)


def test_storage_round_trip():
    schedule = r.parse_schedule("every other monday and thursday at 7pm")
    assert r.Schedule.from_storage(*schedule.to_storage()) == schedule


def test_next_occurrence_and_summer_time():
    mondays = r.parse_schedule("mondays at 1800")
    first = r.next_occurrence(mondays, datetime(2026, 9, 28, 16, 0, tzinfo=timezone.utc), UK)  # 17:00 BST
    assert first == datetime(2026, 9, 28, 17, 0, tzinfo=timezone.utc)  # 18:00 BST
    # The clocks go back on 25 Oct 2026: 18:00 local becomes 18:00 UTC.
    after_change = r.next_occurrence(mondays, datetime(2026, 10, 20, tzinfo=timezone.utc), UK)
    assert after_change == datetime(2026, 10, 26, 18, 0, tzinfo=timezone.utc)


def test_fortnightly_uses_anchor():
    fridays = r.parse_schedule("every other friday at 7pm")
    t, seen = datetime(2026, 9, 28, tzinfo=timezone.utc), []
    for _ in range(3):
        t = r.next_occurrence(fridays, t, UK, anchor=date(2026, 10, 2))
        seen.append(t.astimezone(UK).date())
    assert seen == [date(2026, 10, 2), date(2026, 10, 16), date(2026, 10, 30)]


@pytest.mark.parametrize("text, expected", [
    ("19 oct", date(2026, 10, 19)), ("oct 19", date(2026, 10, 19)), ("19th October", date(2026, 10, 19)),
    ("19/10", date(2026, 10, 19)), ("19/10/26", date(2026, 10, 19)), ("2026-10-19", date(2026, 10, 19)),
    ("today", date(2026, 9, 28)), ("tomorrow", date(2026, 9, 29)), ("5 jan", date(2027, 1, 5)),
])
def test_parse_date(text, expected):
    assert r.parse_date(text, date(2026, 9, 28)) == expected


@pytest.mark.parametrize("text", ["31/02", "1/9/2026", "blah", "19 foo"])
def test_parse_date_errors(text):
    with pytest.raises(r.ScheduleError):
        r.parse_date(text, date(2026, 9, 28))


def test_start_date_for_fortnightly():
    schedule = r.parse_schedule("every other monday at 7pm")
    first, anchor = r.first_on_or_after(schedule, date(2026, 10, 19), datetime(2026, 9, 28, tzinfo=timezone.utc), UK)
    assert first.astimezone(UK).date() == date(2026, 10, 19)
    assert r.next_occurrence(schedule, first, UK, anchor).astimezone(UK).date() == date(2026, 11, 2)


@pytest.mark.parametrize("text, rest, minutes", [
    ("mondays at 1900, 15 minutes before", "mondays at 1900", 15),
    ("mondays 7pm 15m before", "mondays 7pm", 15),
    ("monday 1900 remind 1h before", "monday 1900", 60),
    ("mondays 9pm, reminder 20m before", "mondays 9pm", 20),
    ("mondays 19:00 half an hour before", "mondays 19:00", 30),
    ("mondays at 1900 1 hour 30 minutes before", "mondays at 1900", 90),
    ("mondays 7pm, 1 day before", "mondays 7pm", 1440),
    ("mondays at 1900", "mondays at 1900", None),
])
def test_split_lead(text, rest, minutes):
    assert r.split_lead(text) == (rest, minutes)


def test_lead_limit():
    with pytest.raises(r.ScheduleError, match="48 hours"):
        r.split_lead("mondays 7pm, 3 days before")


@pytest.mark.parametrize("minutes, described", [
    (0, "at the start time"), (15, "15 minutes before"), (60, "1 hour before"),
    (90, "1 hour 30 minutes before"), (1440, "1 day before"), (1560, "26 hours before"),
])
def test_describe_lead(minutes, described):
    assert r.describe_lead(minutes) == described
