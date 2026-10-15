"""What the 📜 Old books dictionaries share (ktdi.oldbooks), and building them from Gutenberg (ktdi.tools.gutenberg)."""

import pytest

from ktdi import oldbooks
from ktdi.tools import gutenberg

EEL = {"word": "Eel", "text": "To dream of an eel is good if you can maintain your grip on him."}
CAVE = {"word": "Cavern or Cave", "text": "To be in a cave foreshadows change."}
BABY = {"word": "Baby Carriages", "text": "A congenial friend who will devise pleasurable surprises."}
REASON_V = {"word": "REASON", "text": "To weigh probabilities in the scales of desire."}
REASON_N = {"word": "REASON", "text": "Propensitate of prejudice."}
I = {"word": "I", "text": "The first letter of the alphabet."}


@pytest.fixture
def book():
    return oldbooks.Dictionary([EEL, CAVE, BABY, REASON_V, REASON_N, I], names=lambda e: e["word"].split(" or "),
                               text=lambda e: e["text"])


def test_look_up_by_name(book):
    assert book.look_up("eel").kind == "exact" and book.look_up("eel").entries == [EEL]
    assert book.look_up("cave").entries == [CAVE]  # Either of its names
    assert book.look_up("Cavern").entries == [CAVE]
    assert book.look_up("reason").entries == [REASON_V, REASON_N]  # Every entry with that name
    assert book.look_up("I").entries == [I]  # A name fuzzy matching would skip as filler


def test_look_up_falls_back_to_uses_then_spelling(book):
    assert book.look_up("prejudice").kind == "uses" and book.look_up("prejudice").entries == [REASON_N]
    assert book.look_up("eell").kind == "close" and book.look_up("eell").entries == [EEL]
    assert book.look_up("zzqx") is None


def test_named_in_finds_a_name_anywhere_in_what_was_typed(book):
    assert book.named_in("I dreamt about baby carriages again") == [BABY]  # The longest name wins over "I"
    assert book.named_in("there were eels everywhere") == [EEL]  # Plural
    assert book.named_in("I was in a cave") == [CAVE]
    assert book.named_in("nothing here") == []


def test_same_name_and_uses(book):
    assert book.same_name(REASON_N) == [REASON_V, REASON_N]
    assert book.same_name(EEL) == [EEL]
    assert book.uses("prejudice") == [REASON_N]
    assert book.uses("prejudice", leave_out=REASON_N) == []


def test_autocomplete(book):
    assert [c.value for c in book.autocomplete("ca")] == ["Cave", "Cavern", "Baby Carriages"]  # Starts, then contains
    assert {c.value for c in book.autocomplete("")} == {"Eel", "Cavern", "Cave", "Baby Carriages", "REASON", "I"}


def test_fit_keeps_whole_paragraphs():
    assert oldbooks.fit(["One.", "Two."], 100) == "One.\n\nTwo."
    assert oldbooks.fit(["One.", "Two " * 30], 50) == "One." + oldbooks.MORE
    long = oldbooks.fit(["Word " * 50], 40)
    assert long.startswith("Word Word") and long.endswith("…" + oldbooks.MORE) and len(long) < 40 + len(oldbooks.MORE)


def test_uses_embed_links_each_entry(monkeypatch):
    monkeypatch.setattr(oldbooks.random, "sample", lambda options, n: list(options)[:n])
    found = [{"word": f"W{n}", "text": "x " * 100} for n in range(10)]
    embed = oldbooks.uses_embed(found, query="x", title="Uses", name=lambda e: e["word"], text=lambda e: e["text"],
                                link=lambda e: f"https://book.example/{e['word']}", source="Book",
                                colour=oldbooks.discord.Color.purple())
    lines = embed.description.split("\n")
    assert len(lines) == oldbooks.SHOWN and lines[0].startswith("**[W0](https://book.example/W0)**: x x")
    assert all(len(line) - len("(https://book.example/W0)") <= oldbooks.LINE_LENGTH + 6 for line in lines)
    assert embed.url is None  # The list isn't one place in the book: each entry links to its own
    assert embed.footer.text == "Book. Showing 8 of 10: ask again for others."
    assert oldbooks.uses_embed(found[:2], query="x", title="Uses", name=lambda e: e["word"], text=lambda e: "x",
                               link=lambda e: "https://book.example", source="Book",
                               colour=oldbooks.discord.Color.purple()).footer.text == "Book"


def test_a_list_shows_where_each_entry_mentions_the_word():
    verse = "By Abracadabra we signify\nAn infinite number of things.\n" + "A line of verse.\n" * 8 + \
            "His beard was long and white\nAnd his eyes uncommonly bright.\nMore verse after."
    assert oldbooks.mention(verse, "bright") == "…And his eyes uncommonly bright. More verse after."
    assert oldbooks.mention("Bright and early. Then more.", "bright") == "Bright and early. Then more."  # Early on
    assert oldbooks.mention("No word here at all.", "bright") == "No word here at all."
    long = "word " * 60 + "bright end"  # No sentence break near it: a few words before
    assert oldbooks.mention(long, "bright").startswith("…word") and oldbooks.mention(long, "bright").endswith("end")


def test_shown_typed():
    assert oldbooks.shown_typed("  the   *drunk*  ") == r"the \*drunk\*"


# --- Building from Gutenberg ---
def test_gutenberg_sources_fall_back_to_the_mirror():
    assert gutenberg.source_urls(926) == [
        "https://www.gutenberg.org/cache/epub/926/pg926.txt",
        "https://gutenberg.pglaf.org/9/2/926/926-0.txt",
        "https://gutenberg.pglaf.org/9/2/926/926.txt",
    ]
    assert gutenberg.source_urls(5402)[1] == "https://gutenberg.pglaf.org/5/4/0/5402/5402-0.txt"


def test_download_tries_each_source(monkeypatch):
    tried = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return "The book".encode("utf-8")

    def urlopen(url, timeout):
        tried.append(url)
        if "gutenberg.org" in url:
            raise gutenberg.urllib.error.HTTPError(url, 503, "Service Unavailable", None, None)
        return Response()

    monkeypatch.setattr(gutenberg.urllib.request, "urlopen", urlopen)
    assert gutenberg.download(926) == "The book"
    assert len(tried) == 2  # gutenberg.org, then the mirror


def test_kept_is_the_allowlist_in_book_order():
    entries = [{"word": "A"}, {"word": "B"}, {"word": "A"}, {"word": "C"}]
    assert gutenberg.kept(entries, ["C", "A"]) == [{"word": "A"}, {"word": "A"}, {"word": "C"}]


def test_one_of_picks_a_passage_and_counts_the_rest(book, monkeypatch):
    monkeypatch.setattr(oldbooks.random, "choice", lambda options: options[0])
    assert book.one_of("reason") == (REASON_V, 1)  # Two entries with the name: the first, and one more
    assert book.one_of("eel") == (EEL, 0)
    assert book.one_of(None) == (EEL, 0)  # Nothing asked: any
    assert book.one_of("zzqx") is None


def test_one_of_a_name_spelt_nearly_brings_all_filed_under_it(book, monkeypatch):
    monkeypatch.setattr(oldbooks.random, "choice", lambda options: options[0])
    assert book.one_of("reasn") == (REASON_V, 1)  # Close to REASON: both REASON entries, not just the one matched
    lamps = [{"name": "Lamp", "also": [], "text": "A lamp of dog's faces."},
             {"name": "Lamp", "also": ["Fart"], "text": "A lamp that makes you fart."}]
    secrets = oldbooks.Dictionary(lamps, names=lambda s: [s["name"], *s["also"]], text=lambda s: s["text"])
    assert secrets.one_of("fart") == (lamps[1], 0)  # Found by another name: only what's filed under that one


def test_close_first_can_be_turned_off_for_one_look_up():
    book = oldbooks.Dictionary([EEL, CAVE], names=lambda e: e["word"].split(" or "), text=lambda e: e["text"],
                               close_first=True)
    assert book.look_up("caves").kind == "close"  # The command: a name spelt like it first
    found = book.look_up("cave", close_first=False)
    assert found.kind == "exact"  # An exact name still wins
    assert book.look_up("caver", close_first=False).kind == "close"  # Nothing uses it: spelt like it, as ever
    assert book.look_up("eell").entries == [EEL]


def test_modern_spelling_is_for_searching_old_spelling():
    assert oldbooks.modern_spelling("If thy wyfe loue the Vnicorne, inuisible vnder the fyre, haue a seruant") == \
        "If thy wife love the Unicorne, invisible under the fire, have a servant"
    assert oldbooks.modern_spelling("they eye any true blue vertue") == "they eye any true blue vertue"  # Left be


def test_escape_keeps_the_books_italics_and_dashes():
    assert oldbooks.escape("A _very_ fine*thing -- truly") == r"A *very* fine\*thing—truly"
