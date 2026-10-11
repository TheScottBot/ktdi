"""/almanac: Hone's Every-Day Book day by day (ktdi.features.almanac, ktdi.tools.almanac_build)."""

import json
from datetime import date

import pytest

from ktdi.features import almanac
from ktdi.lib.reminders import ScheduleError, parse_day
from ktdi.tools import almanac_build as build
from tests.fakes import Ctx, User, run

SCOTT = User(1, "scott")

VOLUME_1 = """Preface.

JANUARY, 1825.


~January 22.~

  _St. Vincent._ _St. Anastasius._

St. Vincent was a Spanish martyr, and a crow defended his body from wild beasts and birds of prey, says Butler.

It is thus done into English by Abraham Fleming:

    Remember on St. Vincent’s day
    If that the sun his beams display


CHRONOLOGY.

1800.--On the 22d of January, in this year, died George Steevens, who never took one pinch of snuff after he
lost his box in St. Paul’s church-yard.[7]

FLORAL DIRECTORY.

  _St. Vincent._
  Early Witlow grass. _Draba verna._


~April 1.--All Fools’ Day.~

  _St. Hugh_, Bp. A. D. 1132.

Thirty years ago, when buckles were worn in shoes, a boy would meet a person in the street with "Sir, your
shoe's unbuckled."

FLORAL DIRECTORY.

Annual Mercury. _Mercurialis annua._
Dedicated to _St. Hugh_.

[56] Brand.

*** END OF THE PROJECT GUTENBERG EBOOK
"""

VOLUME_2 = """Preface.

~January 22.~


_St. Vincent._

The barometer in London was at 30·48 in May, and never rose higher during the whole year, Mr. Howard says.

NATURALISTS’ CALENDAR.

Mean Temperature 37·58.

*** END OF THE PROJECT GUTENBERG EBOOK
"""


@pytest.fixture
def days():
    return {**{(d["volume"], d["date"]): d for d in build.days(VOLUME_1, 1)},
            **{(d["volume"], d["date"]): d for d in build.days(VOLUME_2, 2)}}


@pytest.fixture(autouse=True)
def calendar(monkeypatch):
    data = build.build({1: VOLUME_1, 2: VOLUME_2}, {"keep": ["1:01-22:0", "1:01-22:c0", "2:01-22:0", "1:04-01:0"]})
    monkeypatch.setattr(almanac, "DAYS", data["days"])
    monkeypatch.setattr(almanac, "today", lambda: date(2026, 1, 22))
    monkeypatch.setattr(almanac.random, "choice", lambda options: options[0])


# --- Reading the book ---
def test_days_are_read_from_the_book(days):
    vincent = days[(1, "01-22")]
    assert vincent["saints"] == "_St. Vincent._ _St. Anastasius._"
    assert vincent["passages"] == [  # Verse and the line introducing it aren't passages on their own
        "St. Vincent was a Spanish martyr, and a crow defended his body from wild beasts and birds of prey, says Butler.",
        "It is thus done into English by Abraham Fleming:"]
    assert vincent["chronology"][0].startswith("1800.--On the 22d of January")
    assert vincent["flower"] == {"plant": "Early Witlow grass. _Draba verna._", "for": "_St. Vincent._"}
    assert vincent["temperature"] is None and vincent["name"] is None
    fools = days[(1, "04-01")]
    assert fools["name"] == "All Fools’ Day"
    assert fools["flower"] == {"plant": "Annual Mercury. _Mercurialis annua._", "for": "_St. Hugh_"}  # Either order
    second = days[(2, "01-22")]
    assert second["saints"] == "_St. Vincent._" and second["temperature"] == 37.58  # Not indented, in volume 2


def test_build_merges_the_volumes_and_keeps_the_allowlist():
    data = build.build({1: VOLUME_1, 2: VOLUME_2}, {"keep": ["1:01-22:c0", "2:01-22:0"]})["days"]
    vincent = data["01-22"]
    assert vincent["temperature"] == 37.58 and vincent["flower"]["plant"].startswith("Early Witlow")  # Both volumes'
    assert [p["volume"] for p in vincent["passages"]] == [1, 2]
    assert vincent["passages"][0]["text"].endswith("St. Paul’s church-yard.")  # Footnote mark taken out
    assert data["04-01"]["passages"] == []


def test_the_real_almanac_is_exactly_whats_on_the_allowlist():
    curation = json.loads(build.CURATION.read_text(encoding="utf-8"))
    assert set(curation) == {"_about", "keep"}
    days = json.loads(almanac.DATA.read_text(encoding="utf-8"))["days"]
    assert len(days) == 365 and "02-29" not in days  # Neither 1825 nor 1826 had one
    assert sum(len(day["passages"]) for day in days.values()) == len(curation["keep"])
    assert sum(1 for day in days.values() if day["passages"]) >= 300
    assert sum(1 for day in days.values() if day["flower"]) >= 300


# --- Dates ---
def test_days_of_the_year():
    today = date(2026, 10, 11)
    assert parse_day("5 november", today) == (11, 5)
    assert parse_day("nov 5th", today) == (11, 5)
    assert parse_day("5/11", today) == (11, 5)
    assert parse_day("1 jan", today) == (1, 1)  # The past is fine: it's a day of the year, not a booking
    assert parse_day("29 feb", today) == (2, 29)
    with pytest.raises(ScheduleError):
        parse_day("30 feb", today)


# --- The command ---
def test_today():
    embed = almanac.almanac_embed(None)
    assert embed.title == "📅 Thursday 22 January"
    assert embed.description == (
        "⛪ *St. Vincent.* *St. Anastasius.*\n\n"
        "St. Vincent was a Spanish martyr, and a crow defended his body from wild beasts and birds of prey, says "
        "Butler.\n\n"
        "🌼 Flower of the day: Early Witlow grass. *Draba verna.* (for *St. Vincent.*)\n\n"
        "🌡️ London's average for the day, 1797–1816: 37.6°F (3.1°C)")
    assert embed.footer.text == f"{almanac.SOURCE}. Ask again for another (3 for this day)."
    assert embed.url.startswith("https://www.gutenberg.org/cache/epub/53275/pg53275-images.html#:~:text=St.%20Vincent")


def test_a_named_day():
    embed = almanac.almanac_embed("1 april")
    assert embed.title == "📅 Wednesday 1 April: All Fools’ Day"
    assert embed.footer.text == almanac.SOURCE  # Just the one passage


def test_a_day_with_nothing():
    assert "Hone skipped this one" in almanac.almanac_embed("29 feb").description
    assert almanac.almanac_embed("29 feb").title == "📅 29 February"  # 2026 has no 29 February to give a weekday
    assert "isn't a real date" in almanac.almanac_embed("30 feb").description
    assert "couldn't read the date" in almanac.almanac_embed("blah").description


def test_command():
    ctx = Ctx(SCOTT)
    run(almanac.almanac.callback(ctx))
    assert ctx.last.embed.title == "📅 Thursday 22 January"
    run(almanac.almanac.callback(ctx, date="1/4"))
    assert ctx.last.embed.title.startswith("📅 Wednesday 1 April")
    assert almanac.almanac.aliases == ["onthisday", "hone"]
