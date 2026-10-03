"""Understanding timezones and times as people type them (ktdi.lib.timezones)."""

from datetime import datetime, time, timezone

import pytest

from ktdi.lib import timezones as tz
from ktdi.lib.timezones import TimezoneError

SUMMER = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
WINTER = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("typed, key", [
    ("London", "Europe/London"), ("  new   york ", "America/New_York"), ("New_York", "America/New_York"),
    ("america/new_york", "America/New_York"), ("TOKYO", "Asia/Tokyo"), ("buenos aires", "America/Argentina/Buenos_Aires"),
    ("EST", "America/New_York"), ("pst", "America/Los_Angeles"), ("BST", "Europe/London"), ("GMT", "Europe/London"),
    ("utc", "UTC"), ("CET", "Europe/Paris"), ("IST", "Asia/Kolkata"),
])
def test_zones_by_name(typed, key):
    assert tz.parse_zone(typed).key == key


@pytest.mark.parametrize("typed, name, hours", [
    ("UTC+2", "UTC+2", 2), ("utc-5", "UTC-5", -5), ("+5:30", "UTC+5:30", 5.5), ("GMT+0530", "UTC+5:30", 5.5),
    ("utc - 3", "UTC-3", -3),
])
def test_offsets(typed, name, hours):
    zone = tz.parse_zone(typed)
    assert zone.tzname(None) == name and zone.utcoffset(None).total_seconds() == hours * 3600
    assert tz.parse_zone(tz.zone_id(zone)) == zone  # stores and loads the same


@pytest.mark.parametrize("typed", ["", "Narnia", "UTC+15", "utc+3:75"])
def test_unknown_zones(typed):
    with pytest.raises(TimezoneError):
        tz.parse_zone(typed)


def test_describe_zone_knows_summer_time():
    london, new_york = tz.parse_zone("London"), tz.parse_zone("EST")
    assert tz.describe_zone(london, SUMMER) == "London (BST)" and tz.describe_zone(london, WINTER) == "London (GMT)"
    assert tz.describe_zone(new_york, SUMMER) == "New York (EDT)" and tz.describe_zone(new_york, WINTER) == "New York (EST)"
    assert tz.describe_zone(tz.parse_zone("utc"), SUMMER) == "UTC"
    assert tz.describe_zone(tz.parse_zone("Dubai"), SUMMER) == "Dubai (UTC+04)"  # no letters, just an offset
    assert tz.describe_zone(tz.parse_zone("UTC+5:30"), SUMMER) == "UTC+5:30"


@pytest.mark.parametrize("typed, expected", [
    ("7pm", time(19)), ("7 PM", time(19)), ("7:30pm", time(19, 30)), ("19:00", time(19)), ("1930", time(19, 30)),
    ("12am", time(0)), ("12pm", time(12)), ("noon", time(12)), ("midnight", time(0)), ("9", time(9)),
    ("now", None), ("19.45", time(19, 45)),
])
def test_clocks(typed, expected):
    assert tz.parse_clock(typed) == expected


@pytest.mark.parametrize("typed", ["13pm", "25:00", "19:60", "teatime", "0am"])
def test_bad_clocks(typed):
    with pytest.raises(TimezoneError):
        tz.parse_clock(typed)


def test_convert():
    start, end = tz.convert(time(19), tz.parse_zone("London"), tz.parse_zone("New York"), SUMMER)
    assert (start.strftime("%H:%M %d"), end.strftime("%H:%M %d")) == ("19:00 01", "14:00 01")
    start, end = tz.convert(time(23), tz.parse_zone("London"), tz.parse_zone("Tokyo"), WINTER)
    assert end.strftime("%H:%M") == "08:00" and tz.day_note(start, end) == " (the next day)"
    start, end = tz.convert(time(1), tz.parse_zone("London"), tz.parse_zone("PST"), WINTER)
    assert end.strftime("%H:%M") == "17:00" and tz.day_note(start, end) == " (the day before)"
    start, end = tz.convert(None, tz.parse_zone("UTC"), tz.parse_zone("UTC+5:30"), SUMMER)  # now
    assert (start.strftime("%H:%M"), end.strftime("%H:%M")) == ("12:00", "17:30")


def test_convert_uses_today_where_its_from():
    # Just after midnight UTC on 2 July is still 1 July in New York: "9pm New York" means the 1st.
    late = datetime(2026, 7, 2, 0, 30, tzinfo=timezone.utc)
    start, _ = tz.convert(time(21), tz.parse_zone("New York"), tz.parse_zone("London"), late)
    assert start.date().isoformat() == "2026-07-01"


def test_suggestions():
    labels = [label for label, _ in tz.suggestions("lond")]
    assert labels[0] == "London (Europe/London)"
    assert tz.suggestions("est")[0] == ("EST (America/New_York)", "America/New_York")
    assert len(tz.suggestions("a")) == 25
