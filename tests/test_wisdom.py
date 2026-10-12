"""/wisdom and Old Wisdom of the Day (ktdi.features.wisdom)."""

from datetime import datetime, timezone

import discord
import pytest

from ktdi import oldbooks
from ktdi.features import wisdom
from tests.fakes import Channel, Ctx, Guild, User, run

SCOTT = User(1, "scott", admin=True)
GUILD = Guild()


def book(command: str) -> oldbooks.OldBook:
    return oldbooks.OldBook(f"The Book of {command}", "📕", command, random=lambda: discord.Embed(title=command))


BOOKS = [book("pliny"), book("dream")]


@pytest.fixture(autouse=True)
def books(monkeypatch):
    monkeypatch.setattr(wisdom, "old_books", lambda: BOOKS)
    monkeypatch.setattr(wisdom.random, "choice", lambda options: options[0])


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


# --- Picking and posting ---
def test_a_book_is_not_picked_two_days_running():
    assert wisdom.pick().command == "pliny"
    assert wisdom.pick("pliny").command == "dream"


def test_only_one_book_is_picked_every_day(monkeypatch):
    monkeypatch.setattr(wisdom, "old_books", lambda: BOOKS[:1])
    assert wisdom.pick("pliny").command == "pliny"


def test_wisdom_now():
    ctx = Ctx(SCOTT, GUILD)
    run(wisdom.wisdom_group.callback(ctx))
    assert ctx.last.content == "📜 **Old wisdom**, from `/pliny`"
    assert ctx.last.embed.title == "pliny"


def test_a_book_can_post_itself():
    """/herbal posts its own (so it can be dug into)."""
    sent = []

    async def send(where, content):
        sent.append((where, content))

    channel = Channel()
    herbal = oldbooks.OldBook("Herbal", "🌱", "herbal", random=lambda: discord.Embed(), send=send)
    run(herbal.post(channel, "📜 Heading"))
    assert sent == [(channel, "📜 Heading")] and channel.sent == []


# --- When ---
def test_next_post_is_tomorrow_at_the_time_in_the_bots_timezone():
    assert wisdom.next_post("09:00", at("2026-10-12T07:00")) == at("2026-10-12T08:00")  # 9am BST
    assert wisdom.next_post("09:00", at("2026-10-12T08:00")) == at("2026-10-13T08:00")  # Just posted: tomorrow
    assert wisdom.next_post("09:00", at("2026-10-25T12:00")) == at("2026-10-26T09:00")  # 9am GMT, after the clocks


# --- Setting it up ---
def test_setup_here_at_9am_by_default(monkeypatch):
    monkeypatch.setattr(wisdom, "datetime", type("Now", (), {"now": staticmethod(lambda tz: at("2026-10-12T10:00")),
                                                            "fromisoformat": datetime.fromisoformat}))
    ctx = Ctx(SCOTT, GUILD, channel=Channel(700, GUILD))
    run(wisdom.wisdom_setup_here.callback(ctx))
    setup = wisdom.get_setup(GUILD.id)
    assert (setup.channel_id, setup.clock, setup.set_by) == (700, "09:00", SCOTT.id)
    assert setup.next_run_at == at("2026-10-13T08:00")
    assert "goes to <#700> every day at 09:00 (Europe/London time)" in ctx.last.content
    assert "from 2 old books, a different one each day" in ctx.last.content


def test_setup_here_at_a_time_and_moving_it():
    run(wisdom.wisdom_setup_here.callback(Ctx(SCOTT, GUILD, channel=Channel(700, GUILD))))
    ctx = Ctx(SCOTT, GUILD, channel=Channel(800, GUILD))
    run(wisdom.wisdom_setup_here.callback(ctx, time="7:30pm"))
    setup = wisdom.get_setup(GUILD.id)
    assert (setup.channel_id, setup.clock) == (800, "19:30")
    assert "It's moved here from <#700>." in ctx.last.content


def test_setup_here_needs_a_real_time():
    ctx = Ctx(SCOTT, GUILD)
    run(wisdom.wisdom_setup_here.callback(ctx, time="teatime"))
    assert ctx.last.private and "isn't a time of day" in ctx.last.content
    assert wisdom.get_setup(GUILD.id) is None


def test_show_and_stop():
    ctx = Ctx(SCOTT, GUILD)
    run(wisdom.wisdom_setup_show.callback(ctx))
    assert "isn't set up here" in ctx.last.content
    run(wisdom.wisdom_setup_here.callback(Ctx(SCOTT, GUILD, channel=Channel(700, GUILD))))
    run(wisdom.wisdom_setup_stop.callback(ctx))
    assert "No more Old Wisdom of the Day" in ctx.last.content and wisdom.get_setup(GUILD.id) is None
    run(wisdom.wisdom_setup_stop.callback(ctx))
    assert ctx.last.private and "nothing to stop" in ctx.last.content


def test_only_managers_set_it_up():
    for command in (wisdom.wisdom_setup_here, wisdom.wisdom_setup_stop):
        assert any("has_guild_permissions" in repr(check) for check in command.checks), command.name


# --- The daily post ---
def loop_at(monkeypatch, when: str):
    monkeypatch.setattr(wisdom, "datetime", type("Now", (), {"now": staticmethod(lambda tz: at(when)),
                                                            "fromisoformat": datetime.fromisoformat}))
    run(wisdom.wisdom_loop.coro())


def test_the_daily_post(bot, monkeypatch):
    channel = bot.add_channel(Channel(700, GUILD))
    wisdom.save_setup(GUILD.id, 700, "09:00", at("2026-10-12T08:00"), SCOTT.id)
    loop_at(monkeypatch, "2026-10-12T07:59")
    assert channel.sent == []  # Not yet
    loop_at(monkeypatch, "2026-10-12T08:00")
    assert channel.sent[-1].content == "📜 **Old Wisdom of the Day**, from `/pliny`"
    setup = wisdom.get_setup(GUILD.id)
    assert (setup.next_run_at, setup.last_book) == (at("2026-10-13T08:00"), "pliny")
    loop_at(monkeypatch, "2026-10-13T08:00")
    assert channel.sent[-1].content == "📜 **Old Wisdom of the Day**, from `/dream`"  # A different book
    assert len(channel.sent) == 2


def test_a_day_missed_by_hours_is_skipped_not_posted_late(bot, monkeypatch):
    channel = bot.add_channel(Channel(700, GUILD))
    wisdom.save_setup(GUILD.id, 700, "09:00", at("2026-10-12T08:00"), SCOTT.id)
    loop_at(monkeypatch, "2026-10-12T20:00")
    assert channel.sent == [] and wisdom.get_setup(GUILD.id).next_run_at == at("2026-10-13T08:00")


def test_a_lost_channel_doesnt_stop_the_days_moving_on(bot, monkeypatch):
    wisdom.save_setup(GUILD.id, 999, "09:00", at("2026-10-12T08:00"), SCOTT.id)
    loop_at(monkeypatch, "2026-10-12T08:00")
    assert wisdom.get_setup(GUILD.id).next_run_at == at("2026-10-13T08:00")


def test_the_real_books_can_all_be_posted(bot, monkeypatch):
    monkeypatch.undo()
    for old_book in wisdom.old_books():
        if old_book.command == "herbal":
            continue  # Posts itself: tests/test_herbal.py
        channel = Channel(700, GUILD)
        run(old_book.post(channel, "📜 Heading"))
        assert isinstance(channel.sent[-1].embed, discord.Embed), old_book.command
