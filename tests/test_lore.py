"""/lore, and every old book declaring itself for it and for Old Wisdom of the Day (ktdi.features.lore,
ktdi.oldbooks.OldBook)."""

import importlib
import random

import discord
import pytest

from ktdi import oldbooks
from ktdi.features import FEATURES, lore
from tests.fakes import Ctx, User, run

SCOTT = User(1, "scott")
OLD_BOOK_SECTIONS = {"📚 Words & wisdom", "🐉 Beasts & magic", "🌿 Hearth & herbs"}
NOT_BOOKS = {"ktdi.features.lore", "ktdi.features.wisdom"}  # In an old-book section, but not books


def book(name: str, entries: list[dict]) -> oldbooks.OldBook:
    dictionary = oldbooks.Dictionary(entries, names=lambda e: [e["title"]], text=lambda e: e["text"])
    return oldbooks.OldBook(f"The Book of {name}", "📕", name.lower(), random=lambda: discord.Embed(title=name),
                            find=dictionary.look_up, link=lambda e: f"https://example.org/{e['title']}")


PLINY = book("Pliny", [{"title": "Dragons", "text": "Africa produces dragons."},
                       {"title": "Elephants", "text": "Elephants fear the dragon."}])
DREAMS = book("Dreams", [{"title": "Eels", "text": "To dream of an eel is good, as dragons are bad."},
                         {"title": "Caves", "text": "Dragons live in caves."}])
COOKERY = book("Cookery", [{"title": "Draggle tart", "text": "A tart."}])


@pytest.fixture(autouse=True)
def books(monkeypatch):
    monkeypatch.setattr(lore, "old_books", lambda: [DREAMS, COOKERY, PLINY])
    monkeypatch.setattr(lore.random, "choice", lambda options: options[0])


# --- Every old book takes part ---
def test_every_old_book_declares_itself():
    """A new old book has to declare OLD_BOOK, or /lore and Old Wisdom of the Day won't know it's there."""
    for name in FEATURES:
        module = importlib.import_module(name)
        if getattr(module, "HELP_CATEGORY", None) in OLD_BOOK_SECTIONS and name not in NOT_BOOKS:
            assert hasattr(module, "OLD_BOOK"), f"{name} has no OLD_BOOK"


def test_every_old_book_gives_a_random_entry_and_searches_sensibly(monkeypatch):
    monkeypatch.undo()  # The real books
    random.seed(1)
    found = lore.old_books()
    assert len(found) >= 18 and len({b.command for b in found}) == len(found)
    for old_book in found:
        assert isinstance(old_book.random(), discord.Embed), old_book.command
        if old_book.find:
            hits = old_book.find("love") or old_book.find("dragon") or old_book.find("rose")
            if hits:
                entry = hits.entries[0]
                assert old_book.title(entry) and isinstance(old_book.text(entry), str), old_book.command


# --- /lore ---
def test_books_with_the_thing_come_first_then_those_that_mention_it():
    embed = lore.lore_embed("dragons")
    assert embed.title == "📜 Lore: dragons"
    assert embed.description == "What 2 old books have to say about it."
    assert [f.name for f in embed.fields] == ["📕 The Book of Pliny", "📕 The Book of Dreams"]  # Not "Draggle tart"
    assert embed.fields[0].value == "**[Dragons](https://example.org/Dragons)**: Africa produces dragons."
    assert embed.fields[1].value == ("**[Eels](https://example.org/Eels)**: To dream of an eel is good, as dragons "
                                     "are bad.\n-# …and 1 more: `/dreams dragons`")  # Two that mention it


def test_a_near_spelling_only_when_nothing_has_the_thing():
    names = [f.name for f in lore.lore_embed("dragonz").fields]
    assert "📕 The Book of Pliny" in names


def test_nothing():
    embed = lore.lore_embed("zzqx")
    assert not embed.fields and "None of the old books has anything on that here" in embed.description
    assert "There may be more on it in the books themselves" in embed.description


def test_it_fits_in_an_embed(monkeypatch):
    many = [book(f"Dragons {n}", [{"title": "Dragons", "text": "Dragons. " + "Long " * 300}]) for n in range(25)]
    monkeypatch.setattr(lore, "old_books", lambda: many)
    embed = lore.lore_embed("dragons")
    assert len(embed) <= 6000 and len(embed.fields) == 25  # Every book gets its line...
    monkeypatch.setattr(lore, "old_books", lambda: many[:1])
    alone = lore.lore_embed("dragons").fields[0].value
    assert all(len(f.value) < len(alone) for f in embed.fields)  # ...with a shorter quote than a book on its own


def test_command():
    ctx = Ctx(SCOTT)
    run(lore.lore.callback(ctx, thing="dragons"))
    assert ctx.last.embed.title == "📜 Lore: dragons"
    assert lore.lore.aliases == ["oldbooks"]
