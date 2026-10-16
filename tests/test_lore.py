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


# --- The shelves ---
def shelved(name: str, entries: list[dict], shelves: tuple[str, ...], entry_shelves=lambda e: ()):
    dictionary = oldbooks.Dictionary(entries, names=lambda e: [e["title"]], text=lambda e: e["text"])
    return oldbooks.OldBook(f"The Book of {name}", "📕", name.lower(), random=lambda: discord.Embed(title=name),
                            find=dictionary.look_up, shelves=shelves, entry_shelves=entry_shelves)


SALT = [{"title": "Salt at dinner", "text": "Pass the salt."},
        {"title": "Salt against witches", "text": "Witches hate salt.", "magic": True}]
OMENS = shelved("Omens", SALT, ("folklore",), lambda e: ("esoteric",) if e.get("magic") else ())
SECRETS = shelved("Secrets", [{"title": "Salt of the stars", "text": "A magical salt."}], ("esoteric",))
NATURE = shelved("Nature", [{"title": "Rock salt", "text": "Salt is dug from mines."}], ("nature",))


def test_every_old_book_is_on_a_shelf(monkeypatch):
    monkeypatch.undo()  # The real books
    for old_book in lore.old_books():
        assert old_book.shelves and set(old_book.shelves) <= set(oldbooks.SHELVES), old_book.command


def test_a_shelf_has_its_books_and_the_entries_of_others_on_it(monkeypatch):
    monkeypatch.setattr(lore, "old_books", lambda: [OMENS, SECRETS, NATURE])
    assert [book.command for book, _ in lore.searched("salt")] == ["omens", "secrets", "nature"]
    esoteric = lore.searched("salt", "esoteric")
    assert [(book.command, [e["title"] for e in entries]) for book, entries in esoteric] == [
        ("omens", ["Salt against witches"]), ("secrets", ["Salt of the stars"])]  # Not salt at dinner, nor rock salt
    assert [book.command for book, _ in lore.searched("salt", "folklore")] == ["omens"]
    assert OMENS.find_on("folklore", "salt").entries == SALT  # All of a book on the shelf


def test_a_shelf_page(monkeypatch):
    monkeypatch.setattr(lore, "old_books", lambda: [OMENS, SECRETS, NATURE])
    embed = lore.lore_embed("salt", "esoteric")
    assert embed.title == "🔮 Esoteric: salt"
    assert embed.description == "What 2 old books on the esoteric shelf have to say about it."
    assert embed.footer.text.endswith("or every book with /lore.")
    assert "/esoteric" in lore.lore_embed("salt").footer.text  # /lore points to the shelves
    nothing = lore.lore_embed("zzqx", "nature").description
    assert "Nothing on that on the natural history shelf" in nothing and "picked by hand" in nothing


def test_the_shelf_commands():
    assert [c.name for c in lore.SHELF_COMMANDS] == list(oldbooks.SHELVES)
    for command in lore.SHELF_COMMANDS:
        assert len(command.description) <= 100 and command.help.startswith("/lore, on the")
    ctx = Ctx(SCOTT)
    run(lore.SHELF_COMMANDS[0].callback(ctx, thing="dragons"))
    assert ctx.last.embed.title == "🦉 Natural history: dragons"


def test_the_magic_in_the_folklore_books_is_real():
    from ktdi.features import goblin, omen
    assert {o["key"] for o in omen.OMENS if omen.shelves_of(o)} and \
        {(o["essay"], o["section"]) for o in omen.OMENS} >= omen.MAGIC  # Every subsection named is in the book
    assert goblin.MAGIC <= {t["key"] for t in goblin.TALES}
