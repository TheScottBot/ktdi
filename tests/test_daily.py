"""Posting every day in a channel each server chooses (ktdi.daily): Old Wisdom of the Day and the almanac."""

from datetime import datetime, timezone

import pytest

from ktdi import daily
from ktdi.features import almanac, wisdom
from tests.fakes import Channel, Ctx, Guild, User, run

SCOTT = User(1, "scott", admin=True)
GUILD = Guild()
POSTS = []


async def post(channel, last):
    POSTS.append(last)
    await channel.send(f"Post {len(POSTS)}")
    return f"remember {len(POSTS)}"


TEST = daily.Daily("test", "The test post", "🧪", "test", post=post, note=lambda: "A note.")


@pytest.fixture(autouse=True)
def registered(monkeypatch):
    monkeypatch.setitem(daily.DAILIES, "test", TEST)
    POSTS.clear()


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def now_is(monkeypatch, when: str):
    monkeypatch.setattr(daily, "datetime", type("Now", (), {"now": staticmethod(lambda tz: at(when)),
                                                           "fromisoformat": datetime.fromisoformat}))


# --- When ---
def test_next_post_is_the_next_time_of_day_where_the_bot_is():
    assert daily.next_post("09:00", at("2026-10-12T07:00")) == at("2026-10-12T08:00")  # 9am BST
    assert daily.next_post("09:00", at("2026-10-12T08:00")) == at("2026-10-13T08:00")  # Just posted: tomorrow
    assert daily.next_post("09:00", at("2026-10-25T12:00")) == at("2026-10-26T09:00")  # 9am GMT, after the clocks


# --- Setting it up ---
def test_setup_here_at_9am_by_default(monkeypatch):
    now_is(monkeypatch, "2026-10-12T10:00")
    ctx = Ctx(SCOTT, GUILD, channel=Channel(700, GUILD))
    run(daily.setup_here(ctx, TEST, None))
    setup = daily.get_setup(GUILD.id, "test")
    assert (setup.channel_id, setup.clock, setup.set_by) == (700, "09:00", SCOTT.id)
    assert setup.next_run_at == at("2026-10-13T08:00")
    assert ctx.last.content.startswith("🧪 The test post goes to <#700> every day at 09:00 (Europe/London time).")
    assert "\n-# A note." in ctx.last.content


def test_setup_here_at_a_time_and_moving_it():
    run(daily.setup_here(Ctx(SCOTT, GUILD, channel=Channel(700, GUILD)), TEST, None))
    ctx = Ctx(SCOTT, GUILD, channel=Channel(800, GUILD))
    run(daily.setup_here(ctx, TEST, "7:30pm"))
    setup = daily.get_setup(GUILD.id, "test")
    assert (setup.channel_id, setup.clock) == (800, "19:30")
    assert "It's moved here from <#700>." in ctx.last.content


def test_setup_here_needs_a_real_time():
    ctx = Ctx(SCOTT, GUILD)
    run(daily.setup_here(ctx, TEST, "teatime"))
    assert ctx.last.private and "isn't a time of day" in ctx.last.content
    assert daily.get_setup(GUILD.id, "test") is None


def test_show_and_stop():
    ctx = Ctx(SCOTT, GUILD)
    run(daily.show(ctx, TEST))
    assert ctx.last.content == ("The test post isn't set up here. Someone with Manage Server can run "
                                "`/test setup here` in the channel it should go to.")
    run(daily.setup_here(Ctx(SCOTT, GUILD, channel=Channel(700, GUILD)), TEST, None))
    run(daily.stop(ctx, TEST))
    assert ctx.last.content.startswith("🧪 The test post won't be posted any more.")
    assert daily.get_setup(GUILD.id, "test") is None
    run(daily.stop(ctx, TEST))
    assert ctx.last.private and "nothing to stop" in ctx.last.content


def test_each_daily_has_its_own_channel_and_time():
    run(daily.setup_here(Ctx(SCOTT, GUILD, channel=Channel(700, GUILD)), wisdom.DAILY, "9am"))
    run(daily.setup_here(Ctx(SCOTT, GUILD, channel=Channel(800, GUILD)), almanac.DAILY, "7am"))
    assert (daily.get_setup(GUILD.id, "wisdom").channel_id, daily.get_setup(GUILD.id, "wisdom").clock) == (700, "09:00")
    assert (daily.get_setup(GUILD.id, "almanac").channel_id, daily.get_setup(GUILD.id, "almanac").clock) == \
        (800, "07:00")


def test_the_setup_commands():
    for group, the_daily in (("wisdom", wisdom.DAILY), ("almanac", almanac.DAILY)):
        module = wisdom if group == "wisdom" else almanac
        ctx = Ctx(SCOTT, GUILD, channel=Channel(700, GUILD))
        run(getattr(module, f"{group}_setup_here").callback(ctx, time="8am"))
        assert daily.get_setup(GUILD.id, the_daily.kind).clock == "08:00"
        run(getattr(module, f"{group}_setup_show").callback(ctx))
        assert "goes to <#700> every day at 08:00" in ctx.last.content
        run(getattr(module, f"{group}_setup_stop").callback(ctx))
        assert daily.get_setup(GUILD.id, the_daily.kind) is None
        for command in ("here", "stop"):  # Only managers set it up
            checks = getattr(module, f"{group}_setup_{command}").checks
            assert any("has_guild_permissions" in repr(check) for check in checks), (group, command)


# --- The daily post ---
def loop_at(monkeypatch, when: str):
    now_is(monkeypatch, when)
    run(daily.daily_loop.coro())


def test_the_daily_post(bot, monkeypatch):
    channel = bot.add_channel(Channel(700, GUILD))
    daily.save_setup(GUILD.id, "test", 700, "09:00", at("2026-10-12T08:00"), SCOTT.id)
    loop_at(monkeypatch, "2026-10-12T07:59")
    assert channel.sent == []  # Not yet
    loop_at(monkeypatch, "2026-10-12T08:00")
    assert [s.content for s in channel.sent] == ["Post 1"]
    setup = daily.get_setup(GUILD.id, "test")
    assert (setup.next_run_at, setup.last) == (at("2026-10-13T08:00"), "remember 1")
    loop_at(monkeypatch, "2026-10-13T08:00")
    assert POSTS == [None, "remember 1"]  # Each day's is told what the day before's remembered


def test_moving_it_keeps_what_it_remembered(monkeypatch):
    daily.save_setup(GUILD.id, "test", 700, "09:00", at("2026-10-12T08:00"), SCOTT.id)
    daily.posted(daily.get_setup(GUILD.id, "test"), at("2026-10-13T08:00"), "pliny")
    run(daily.setup_here(Ctx(SCOTT, GUILD, channel=Channel(800, GUILD)), TEST, "10am"))
    assert daily.get_setup(GUILD.id, "test").last == "pliny"


def test_a_day_missed_by_hours_is_skipped_not_posted_late(bot, monkeypatch):
    channel = bot.add_channel(Channel(700, GUILD))
    daily.save_setup(GUILD.id, "test", 700, "09:00", at("2026-10-12T08:00"), SCOTT.id)
    loop_at(monkeypatch, "2026-10-12T20:00")
    assert channel.sent == [] and daily.get_setup(GUILD.id, "test").next_run_at == at("2026-10-13T08:00")


def test_a_lost_channel_doesnt_stop_the_days_moving_on(bot, monkeypatch):
    daily.save_setup(GUILD.id, "test", 999, "09:00", at("2026-10-12T08:00"), SCOTT.id)
    loop_at(monkeypatch, "2026-10-12T08:00")
    assert daily.get_setup(GUILD.id, "test").next_run_at == at("2026-10-13T08:00")


def test_the_almanac_posts_today(bot, monkeypatch):
    channel = bot.add_channel(Channel(700, GUILD))
    daily.save_setup(GUILD.id, "almanac", 700, "07:00", at("2026-10-12T06:00"), SCOTT.id)
    monkeypatch.setattr(almanac, "today", lambda: datetime(2026, 10, 12).date())
    loop_at(monkeypatch, "2026-10-12T06:00")
    assert channel.sent[-1].content == "📅 **Today in the almanac**"
    assert channel.sent[-1].embed.title.startswith("📅 Monday 12 October")


def test_the_old_wisdom_table_is_moved_across():
    from ktdi import db
    db.conn.execute("CREATE TABLE wisdom_channels (guild_id INTEGER PRIMARY KEY, channel_id INTEGER NOT NULL, "
                    "clock TEXT NOT NULL, next_run TEXT NOT NULL, last_book TEXT, set_by INTEGER NOT NULL)")
    db.conn.execute("INSERT INTO wisdom_channels VALUES (5, 700, '09:00', '2026-10-13T08:00:00+00:00', 'pliny', 1)")
    db._upgrade()
    setup = daily.get_setup(5, "wisdom")
    assert (setup.channel_id, setup.clock, setup.last) == (700, "09:00", "pliny")
    assert not db._columns("wisdom_channels")


def test_the_loop_starts_on_the_minute():
    """So a post due at 9:00 goes just after 9:00, not up to a minute late."""
    from datetime import datetime, timezone
    assert daily.seconds_to_next_minute(datetime(2026, 10, 19, 22, 11, 58, 500_000, tzinfo=timezone.utc)) == 2.0
    assert daily.seconds_to_next_minute(datetime(2026, 10, 19, 22, 12, 0, tzinfo=timezone.utc)) == 60.5
