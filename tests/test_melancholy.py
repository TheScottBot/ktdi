"""/melancholy: Burton's The Anatomy of Melancholy (ktdi.features.melancholy, ktdi.tools.melancholy_build)."""

import json
import types

import pytest

from ktdi.features import melancholy
from ktdi.tools import melancholy_build as build
from tests.fakes import Ctx, User, run

SCOTT = User(1, "scott")

BOOK = """Title page.

DEMOCRITUS JUNIOR TO THE READER.

Gentle reader, I presume thou wilt be very inquisitive to know what
antic or personate actor this is.[1] I write of melancholy, by being
busy to avoid melancholy.

THE FIRST PARTITION.


THE FIRST SECTION, MEMBER, SUBSECTION.

_Man's Excellency, Fall, Miseries_.

Man the most excellent and noble creature of the world.

SUBSECT. V.—_Bad Air, a cause of
Melancholy_.

Air is a cause of great moment. [1505]If it be impure and foggy, it dejects
the spirits. They tarry too long in the sun.


Notes

1. A note.

*** END OF THE PROJECT GUTENBERG EBOOK
"""

KEEP = {
    "Democritus Junior to the Reader": ["I write of melancholy, by being busy to avoid melancholy."],
    "Bad Air, a cause of Melancholy": ["If it be impure and foggy, it dejects\nthe spirits."],  # Wrapped, as copied
}


@pytest.fixture(autouse=True)
def passages(monkeypatch):
    data = build.build(BOOK, {"keep": KEEP})
    monkeypatch.setattr(melancholy, "DICTIONARY", melancholy.dictionary(data["passages"]))
    monkeypatch.setattr(melancholy.oldbooks.random, "choice", lambda options: options[0])


# --- Reading the book ---
def test_the_book_is_split_into_its_subsections():
    parts = build.subsections(BOOK)
    assert [p["title"] for p in parts] == ["Democritus Junior to the Reader", "Man's Excellency, Fall, Miseries",
                                           "Bad Air, a cause of Melancholy"]  # A title over two lines is one
    assert parts[2]["text"] == ("Air is a cause of great moment. If it be impure and foggy, it dejects the spirits. "
                                "They tarry too long in the sun.")  # Footnote marks out


def test_excerpts_must_be_in_the_book_word_for_word():
    data = build.build(BOOK, {"keep": {**KEEP, "Bad Air, a cause of Melancholy": [
        "If it be impure and foggy, it dejects the spirits.", "If it be impure, it dejects the spirits."]}})
    assert [p["text"] for p in data["passages"]] == [
        "I write of melancholy, by being busy to avoid melancholy.",
        "If it be impure and foggy, it dejects the spirits."]
    assert data["missing"] == ["Bad Air, a cause of Melancholy: If it be impure, it dejects the spirits."]


def test_the_real_passages_are_on_the_allowlist():
    curation = json.loads(build.CURATION.read_text(encoding="utf-8"))
    real = json.loads(melancholy.DATA.read_text(encoding="utf-8"))["passages"]
    assert len(real) == sum(len(excerpts) for excerpts in curation["keep"].values()) and len(real) >= 200
    for passage in real:
        assert passage["text"] in curation["keep"][passage["title"]] or \
            passage["text"] in [" ".join(e.split()) for e in curation["keep"][passage["title"]]]


# --- The command ---
def test_a_topic():
    embed = melancholy.melancholy_embed("bad air")
    assert embed.title == "🖤 Bad Air, a cause of Melancholy"
    assert embed.description == "If it be impure and foggy, it dejects the spirits."
    assert embed.footer.text == melancholy.SOURCE
    # The page keeps the footnote mark ("[1505] “If it be..."), so the link finds it from the words after it.
    assert embed.url == ("https://www.gutenberg.org/cache/epub/10800/pg10800-images.html#:~:text="
                         "it%20be%20impure%20and%20foggy%2C%20it%20dejects%20the%20spirits.")


def test_link_anchors_avoid_footnote_marks():
    marked = "Or as he did, of whom [63] Felix Plater speaks, that thought he had frogs in his belly, still crying."
    excerpt = "Or as he did, of whom Felix Plater speaks, that thought he had frogs in his belly, still crying."
    assert build.anchor(excerpt, marked) == "Felix Plater speaks, that thought he had frogs in his"  # Ten words
    assert build.anchor("Not in it at all, so the excerpt's own words.", marked) == \
        "Not in it at all, so the"  # The longest plain run, up to the word with an apostrophe


def test_a_word_in_a_passage():
    assert melancholy.melancholy_embed("busy").title == "🖤 Democritus Junior to the Reader"


def test_random_and_nothing():
    assert melancholy.melancholy_embed(None).title == "🖤 Democritus Junior to the Reader"
    assert "found nothing to be melancholy about" in melancholy.melancholy_embed("zzqx").description


def test_command_and_autocomplete():
    ctx = Ctx(SCOTT)
    run(melancholy.melancholy.callback(ctx, topic="air"))
    assert ctx.last.embed.title == "🖤 Bad Air, a cause of Melancholy"
    choices = run(melancholy.topic_autocomplete(types.SimpleNamespace(), "air"))
    assert [c.value for c in choices] == ["Bad Air, a cause of Melancholy"]
    assert melancholy.melancholy.aliases == ["burton", "gloom"]
