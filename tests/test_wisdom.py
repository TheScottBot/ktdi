"""/wisdom: Old wisdom from any of the old books (ktdi.features.wisdom; posting it every day is tests/test_daily.py)."""

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


def test_the_daily_post_remembers_the_book():
    channel = Channel(700, GUILD)
    assert run(wisdom.DAILY.post(channel, None)) == "pliny"
    assert run(wisdom.DAILY.post(channel, "pliny")) == "dream"
    assert channel.sent[-1].content == "📜 **Old Wisdom of the Day**, from `/dream`"
    assert wisdom.DAILY.note() == "It comes from 2 old books, a different one each day."


def test_a_book_can_post_itself():
    """/herbal posts its own (so it can be dug into)."""
    sent = []

    async def send(where, content):
        sent.append((where, content))

    channel = Channel()
    herbal = oldbooks.OldBook("Herbal", "🌱", "herbal", random=lambda: discord.Embed(), send=send)
    run(herbal.post(channel, "📜 Heading"))
    assert sent == [(channel, "📜 Heading")] and channel.sent == []


def test_the_real_books_can_all_be_posted(monkeypatch):
    monkeypatch.undo()
    for old_book in wisdom.old_books():
        if old_book.command == "herbal":
            continue  # Posts itself: tests/test_herbal.py
        channel = Channel(700, GUILD)
        run(old_book.post(channel, "📜 Heading"))
        assert isinstance(channel.sent[-1].embed, discord.Embed), old_book.command
