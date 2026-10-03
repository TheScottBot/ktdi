"""/timezone (ktdi.features.timezones)."""

import types
from datetime import datetime, timezone

import pytest

from ktdi import db
from ktdi.features import timezones
from tests.fakes import Ctx, Guild, User, run

SCOTT, DAVE = User(1, "scott"), User(2, "dave")
SUMMER_NOON = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def summer(monkeypatch):
    monkeypatch.setattr(timezones, "now", lambda: SUMMER_NOON)


def convert(time, from_zone, to_zone=None, user=SCOTT):
    ctx = Ctx(user)
    run(timezones.timezone_convert.callback(ctx, time, from_zone, to_zone=to_zone))
    return ctx.last


def test_convert():
    reply = convert("7pm", "London", "New York")
    expected_moment = int(datetime(2026, 7, 1, 18, 0, tzinfo=timezone.utc).timestamp())
    assert reply.content == ("🕐 **19:00** in London (BST) is **14:00** in New York (EDT).\n"
                             f"-# That's <t:{expected_moment}:t> where you are.")
    assert not reply.private
    assert "**07:00** (the next day) in Tokyo (JST)" in convert("11pm", "London", "Tokyo").content
    assert "**08:00** in Tokyo (JST)" in convert("midnight", "London", "Tokyo").content


def test_convert_errors_are_private():
    for reply in (convert("teatime", "London", "Paris"), convert("7pm", "Narnia", "Paris"),
                  convert("7pm", "London", "Narnia")):
        assert reply.private and "I don't" in reply.content


def test_needs_a_from_or_a_to():
    for reply in (convert(None, None), convert("7pm", None)):
        assert reply.private and "Give at least a `from` or a `to`" in reply.content


def test_left_out_zones_are_yours():
    ctx = Ctx(SCOTT)
    run(timezones.timezone_set.callback(ctx, zone="tokyo"))
    assert ctx.last.private and ctx.last.content.startswith("🕐 Got it. It's **21:00** on Wed 01 Jul, Tokyo (JST) for you.")
    # No `to`: to yours.
    assert convert("7pm", "EST").content.startswith("🕐 **19:00** in New York (EDT) is **08:00** (the next day) in Tokyo (JST).")
    # No `from`: from yours.
    assert convert("9am", None, "London").content.startswith("🕐 **09:00** in Tokyo (JST) is **01:00** in London (BST).")
    # It's per person: Dave hasn't set one, so his left-out zone is the bot's (London by default).
    assert "in London (BST)" in convert("7pm", "EST", user=DAVE).content


def test_left_out_zones_fall_back_to_the_bots(monkeypatch):
    from ktdi import config
    monkeypatch.setattr(config, "BOT_TIMEZONE", timezones.timezones.parse_zone("Paris"))
    assert convert("7pm", "London").content.startswith("🕐 **19:00** in London (BST) is **20:00** in Paris (CEST).")


def test_no_time_means_now():
    reply = convert(None, None, "Tokyo")  # it's 12:00 UTC: 13:00 in London (the bot's), 21:00 in Tokyo
    assert reply.content.startswith("🕐 It's **13:00** in London (BST), so **21:00** in Tokyo (JST).")
    assert convert("now", "New York", "London").content.startswith("🕐 It's **08:00** in New York (EDT), so **13:00**")


def test_same_zone_at_both_ends():
    reply = convert("7pm", "London")  # no `to`, and the left-out zone is London too
    assert reply.private and "London (BST) at both ends" in reply.content


def test_your_timezone_follows_you_between_servers():
    run(timezones.timezone_set.callback(Ctx(SCOTT, Guild(111)), zone="Tokyo"))
    ctx = Ctx(SCOTT, Guild(222))
    run(timezones.timezone_convert.callback(ctx, "9am", "London"))
    assert "in Tokyo (JST)" in ctx.last.content


def test_set_rejects_nonsense_and_clear_forgets():
    ctx = Ctx(SCOTT)
    run(timezones.timezone_set.callback(ctx, zone="Narnia"))
    assert ctx.last.private and timezones.get_user_zone(SCOTT.id) is None
    run(timezones.timezone_set.callback(ctx, zone="UTC+5:30"))
    assert timezones.get_user_zone(SCOTT.id).tzname(None) == "UTC+5:30"
    run(timezones.timezone_clear.callback(ctx))
    assert timezones.get_user_zone(SCOTT.id) is None and ctx.last.private


def test_show():
    ctx = Ctx(SCOTT)
    run(timezones.timezone_show.callback(ctx))
    assert "You haven't set a timezone" in ctx.last.content
    run(timezones.timezone_show.callback(ctx, DAVE))
    assert "dave hasn't set a timezone" in ctx.last.content
    run(timezones.timezone_set.callback(Ctx(DAVE), zone="New York"))
    run(timezones.timezone_show.callback(ctx, DAVE))
    assert ctx.last.content == "🕐 It's **08:00** on Wed 01 Jul, New York (EDT) for <@2>."
    assert ctx.last.allowed_mentions.users is False  # no ping
    bare = Ctx(DAVE)
    run(timezones.timezone_group.callback(bare))  # bare /timezone shows yours
    assert bare.last.content.endswith("New York (EDT) for <@2>.")


def test_stored_once_per_person():
    run(timezones.timezone_set.callback(Ctx(SCOTT), zone="London"))
    run(timezones.timezone_set.callback(Ctx(SCOTT), zone="Paris"))
    assert db.conn.execute("SELECT user_id, zone FROM user_timezones").fetchall() == [(1, "Europe/Paris")]


def test_autocomplete():
    choices = run(timezones.zone_autocomplete(types.SimpleNamespace(), "new y"))
    assert choices[0].name == "New York (America/New_York)" and choices[0].value == "America/New_York"


def test_logs_who_but_not_where(caplog):
    caplog.set_level("INFO", logger="ktdi")
    run(timezones.timezone_set.callback(Ctx(SCOTT), zone="Tokyo"))
    assert "scott set their timezone" in caplog.text and "Tokyo" not in caplog.text
