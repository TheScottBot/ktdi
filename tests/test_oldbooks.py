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


def test_uses_embed(monkeypatch):
    monkeypatch.setattr(oldbooks.random, "sample", lambda options, n: list(options)[:n])
    found = [{"word": f"W{n}", "text": "x " * 100} for n in range(10)]
    embed = oldbooks.uses_embed(found, title="Uses", line=lambda e: f"**{e['word']}**: {e['text']}", source="Book",
                                url=None, colour=oldbooks.discord.Color.purple())
    lines = embed.description.split("\n")
    assert len(lines) == oldbooks.SHOWN and all(len(line) <= oldbooks.LINE_LENGTH for line in lines)
    assert embed.footer.text == "Book. Showing 8 of 10: ask again for others."
    assert oldbooks.uses_embed(found[:2], title="Uses", line=lambda e: e["word"], source="Book", url=None,
                               colour=oldbooks.discord.Color.purple()).footer.text == "Book"


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
