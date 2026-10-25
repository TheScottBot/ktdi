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
NOT_BOOKS = {"ktdi.features.lore", "ktdi.features.wisdom", "ktdi.features.bread"}  # In an old-book section, not books


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
    commands_ = lore.shelf_commands()
    assert [c.name for c in commands_] == list(oldbooks.SHELVES)
    for command in commands_:
        assert len(command.description) <= 100 and command.help.startswith("The ")
    ctx = Ctx(SCOTT)
    run(commands_[0].callback(ctx, thing="dragons"))
    assert ctx.last.embed.title == "🦉 Natural history: dragons"


def test_how_to_ask_a_book():
    assert PLINY.asked() == "/pliny" and PLINY.asked("dragons") == "/pliny dragons"
    talismans = oldbooks.OldBook("Talismans", "🧿", "talisman", random=lambda: discord.Embed(),
                                 shelves=("esoteric", "folklore"), own_command=False)
    assert talismans.asked() == "/esoteric book:talisman"
    assert talismans.asked("scarab") == "/esoteric book:talisman thing:scarab"
    assert talismans.asked("scarab", "folklore") == "/folklore book:talisman thing:scarab"  # On the shelf asked
    assert talismans.asked("scarab", "nature") == "/esoteric book:talisman thing:scarab"  # Not one of its own


def test_lore_says_how_to_ask_a_book_through_its_shelf(monkeypatch):
    shelf_only = oldbooks.OldBook("The Book of Dreams", "📕", "dreams", random=lambda: discord.Embed(),
                                  find=DREAMS.find, link=DREAMS.link, shelves=("esoteric",), own_command=False)
    monkeypatch.setattr(lore, "old_books", lambda: [shelf_only])
    assert lore.lore_embed("dragons").fields[0].value.endswith(
        "…and 1 more: `/esoteric book:dreams thing:dragons`")


# --- A shelf's books (the real ones, on a real bot) ---
@pytest.fixture(scope="module")
def real_bot():
    from ktdi import daily, db, sessions
    from ktdi.bot import KTDIBot
    from ktdi.features import campaigns
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(campaigns.reminder_loop, "start", lambda: None)  # No background loops in tests
        patch.setattr(daily.daily_loop, "start", lambda: None)
        patch.setattr(sessions.deadline_loop, "start", lambda: None)
        db.init(":memory:")
        bot = KTDIBot()
        run(bot.load_features())
        yield bot


@pytest.fixture
def loaded_bot(monkeypatch, real_bot):
    monkeypatch.undo()  # The real books
    return real_bot


def shelf(bot, name: str):
    return bot.get_command(name)


def test_a_shelf_asks_one_of_its_books_as_its_own_command_would(loaded_bot):
    random.seed(3)
    direct, picked = Ctx(SCOTT, bot=loaded_bot, slash=False), Ctx(SCOTT, bot=loaded_bot)
    run(loaded_bot.get_command("talisman").callback(direct, thing="scarab"))
    run(shelf(loaded_bot, "esoteric").callback(picked, book="talisman", thing="scarab"))
    assert picked.last.embed.title == direct.last.embed.title and "Scarab" in picked.last.embed.title
    run(shelf(loaded_bot, "household").callback(picked, book="beeton recipe", thing="omelet"))  # /beeton itself
    assert "Omelet" in picked.last.embed.title
    run(shelf(loaded_bot, "esoteric").callback(picked, book="cure", thing="a cold"))  # A kept book, asked here too
    assert picked.last.embed.title == "🌿 A cure for a cold"
    run(shelf(loaded_bot, "esoteric").callback(picked, book="talisman"))  # Just the book: any of it
    assert picked.last.content is None and picked.last.embed.footer.text.startswith("W. T. and K. Pavitt")


def test_a_shelf_typed_takes_the_book_first(loaded_bot):
    ctx = Ctx(SCOTT, bot=loaded_bot, slash=False)
    esoteric, household = shelf(loaded_bot, "esoteric"), shelf(loaded_bot, "household")
    for book, thing in [("talisman", "scarab"), ("amulet", "scarab"), ("Talismans", "scarab")]:  # Any of its names
        run(esoteric.callback(ctx, book=book, thing=thing))
        assert ctx.last.embed.title.startswith("🧿"), book  # A talisman on it (any of the passages that are)
    run(household.callback(ctx, book="beeton", thing="advice the housekeeper"))  # "beeton advice", not "beeton"
    assert ctx.last.embed.footer.text.startswith("Mrs Beeton") or "Housekeeper" in ctx.last.embed.title
    run(household.callback(ctx, book="beeton", thing="omelet"))  # Just "beeton" is its recipes
    assert "Omelet" in ctx.last.embed.title
    run(esoteric.callback(ctx, book="salt"))  # Not a book: the whole shelf
    assert ctx.last.embed.title == "🔮 Esoteric: salt"
    run(esoteric.callback(ctx, book="the", thing="moon"))
    assert ctx.last.embed.title == "🔮 Esoteric: the moon"


def test_a_shelf_on_its_own_is_any_of_its_books(loaded_bot):
    ctx = Ctx(SCOTT, bot=loaded_bot)
    for seed in range(8):
        random.seed(seed)
        run(shelf(loaded_bot, "esoteric").callback(ctx))
        assert ctx.last.content.startswith("🔮 From the esoteric shelf: `/")  # Saying which book, and how to ask it


def test_every_book_a_shelf_offers_can_be_asked(loaded_bot):
    """Every book in a shelf's menu has its entries to suggest, and answers when picked with one of them."""
    ctx = Ctx(SCOTT, bot=loaded_bot)
    for command in loaded_bot.tree.get_commands():
        if command.name not in oldbooks.SHELVES:
            continue
        menu = next(p for p in command.parameters if p.name == "book").choices
        offered = [choice.value for choice in menu]
        assert offered == [b.command for b in lore.askable(command.name)] and len(offered) <= 25, command.name
        assert all(len(choice.name) <= 100 for choice in menu)
        assert [p.name for p in command.parameters] == ["book", "thing"]  # The book first, so thing: follows it
        for book in lore.askable(command.name):
            assert book.names(), f"{book.command} has nothing to suggest"
            sent = len(ctx.sent)
            run(loaded_bot.get_command(command.name).callback(ctx, book=book.command, thing=book.names()[0]))
            assert len(ctx.sent) == sent + 1 and (ctx.last.embed or ctx.last.view), book.command


def test_a_shelf_suggests_the_picked_books_entries(monkeypatch):
    monkeypatch.undo()  # The real books
    random.seed(1)
    from ktdi.features import gem, talisman

    def suggested(book, typed):
        return [choice.value for choice in lore.suggestions("esoteric", book, typed)]
    assert suggested("talisman", "scar") == ["scarab", "The Scarab of Khepera"]
    assert set(suggested("talisman", "s")) <= set(talisman.DICTIONARY.names)
    assert suggested("gemlore", "s") and set(suggested("gemlore", "s")) <= set(gem.DICTIONARY.names)
    every = suggested(None, "scar")  # No book picked: every book's on the shelf
    assert "The Scarab of Khepera" in every and any(name not in talisman.DICTIONARY.names for name in every)
    assert len(lore.suggestions("words", None, "")) == 25 and len(lore.suggestions("words", "devils", "")) == 25


def test_a_book_asked_through_its_shelf_has_no_slash_command(loaded_bot):
    """A book's own_command says whether it has a slash command of its own: the rest are typed-only, and asked on
    their shelf."""
    slash = {command.name for command in loaded_bot.tree.get_commands()}
    for book in lore.old_books():
        root = book.command.split()[0]
        assert (root in slash) == book.own_command, book.command
        assert loaded_bot.get_command(root), book.command  # Still typed: !talisman
        if not book.own_command:
            assert oldbooks.shelved(book.command) is book and book.find, book.command
    assert oldbooks.shelved("pliny") is None


def test_the_magic_in_the_folklore_books_is_real():
    from ktdi.features import goblin, omen
    assert {o["key"] for o in omen.OMENS if omen.shelves_of(o)} and \
        {(o["essay"], o["section"]) for o in omen.OMENS} >= omen.MAGIC  # Every subsection named is in the book
    assert goblin.MAGIC <= {t["key"] for t in goblin.TALES}
