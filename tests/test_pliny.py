"""/pliny: Pliny the Elder's Natural History (ktdi.features.pliny, ktdi.tools.pliny_build)."""

import json
import types

import pytest

from ktdi.features import pliny
from ktdi.tools import pliny_build as build
from tests.fakes import Ctx, User, run

SCOTT = User(1, "scott")

VOLUME = """Contents.

  BOOK VIII.

  1. Elephants                                                117


BOOK VII.[835]

MAN.

CHAP. 1.—MAN.

The first place will be justly assigned to man.[1]


BOOK VIII.

THE NATURE OF THE TERRESTRIAL ANIMALS.


CHAP. 1. (1.)—ELEPHANTS; THEIR CAPACITY.


The elephant is the largest of them all, and it has a religious respect also for
the stars, and a veneration for the sun and the moon.[1570] It is said by some authors.

They pay homage to the king.


CHAP. 3. (3.)—THE DOCILITY OF THE
ELEPHANT.


One of these animals was found conning over his lesson in the night-time.


CHAP 90.—THE PHŒNIX.


Æthiopia produces the phœnix, though I am not quite sure that its existence is not all a fable.


FOOTNOTES:

[1] A note.

*** END OF THE PROJECT GUTENBERG EBOOK
"""


@pytest.fixture(autouse=True)
def chapters(monkeypatch):
    found = build.build({60230: VOLUME}, {"keep": ["VIII.1", "VIII.3", "VIII.90"]})["chapters"]
    monkeypatch.setattr(pliny, "DICTIONARY", pliny.dictionary(found))
    monkeypatch.setattr(pliny.oldbooks.random, "choice", lambda options: options[0])


# --- Reading the book ---
def test_chapters_are_read_from_the_book():
    found = {c["key"]: c for c in build.chapters(VOLUME, 60230)}
    assert sorted(found) == ["VII.1", "VIII.1", "VIII.3", "VIII.90"]  # Not the contents, and "CHAP 90." too
    elephants = found["VIII.1"]
    assert elephants["title"] == "Elephants; their capacity" and elephants["volume"] == 60230
    assert elephants["text"] == ("The elephant is the largest of them all, and it has a religious respect also for "
                                 "the stars, and a veneration for the sun and the moon. It is said by some authors."
                                 "\n\nThey pay homage to the king.")  # Footnote marks out, paragraphs kept
    assert elephants["anchor"] == "The elephant is the largest of them all, and it"  # From the page as it is
    assert found["VIII.3"]["title"] == "The docility of the elephant"  # A title over two lines


def test_build_keeps_the_allowlist():
    kept = build.build({60230: VOLUME}, {"keep": ["VIII.3"]})["chapters"]
    assert [c["key"] for c in kept] == ["VIII.3"]


def test_the_real_chapters_are_on_the_allowlist():
    curation = json.loads(build.CURATION.read_text(encoding="utf-8"))
    assert set(curation) == {"_about", "keep"}
    real = json.loads(pliny.DATA.read_text(encoding="utf-8"))["chapters"]
    assert [c["key"] for c in real] == curation["keep"] and len(real) >= 400
    assert all(c["volume"] in build.VOLUMES and c["title"] and c["text"] for c in real)
    assert sum("#:~:text=" in pliny.url(c) for c in real) >= len(real) * 0.95


# --- The command ---
def test_a_topic():
    embed = pliny.pliny_embed("elephant")
    assert embed.title == "🏛️ Elephants; their capacity"
    assert embed.description.startswith("The elephant is the largest of them all")
    assert embed.footer.text == f"{pliny.SOURCE}, book 8, chapter 1. He has more on that: ask again (2 chapters)."
    assert embed.url == ("https://www.gutenberg.org/cache/epub/60230/pg60230-images.html#:~:text="
                         "The%20elephant%20is%20the%20largest%20of%20them%20all%2C%20and%20it")


def test_old_spellings():
    assert pliny.pliny_embed("phoenix").title == "🏛️ The phœnix"  # Typed plainly
    assert pliny.pliny_embed("aethiopia").title == "🏛️ The phœnix"


def test_random_nothing_and_numbers():
    assert pliny.pliny_embed(None).title == "🏛️ Elephants; their capacity"
    assert "Pliny never heard anything about that" in pliny.pliny_embed("zzqx").description
    from ktdi.lib import roman
    assert [roman.to_int(r) for r in ("II", "VIII", "IX", "XIX", "XXXVII", "XL")] == [2, 8, 9, 19, 37, 40]


def test_command_and_autocomplete():
    ctx = Ctx(SCOTT)
    run(pliny.pliny.callback(ctx, topic="docility"))
    assert ctx.last.embed.title == "🏛️ The docility of the elephant"
    choices = run(pliny.topic_autocomplete(types.SimpleNamespace(), "phoe"))
    assert [c.value for c in choices] == ["The phœnix"]
    assert pliny.pliny.aliases == ["naturalhistory"]
