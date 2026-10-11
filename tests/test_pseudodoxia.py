"""/pseudodoxia: Browne's Pseudodoxia Epidemica (ktdi.features.pseudodoxia, ktdi.tools.pseudodoxia_build)."""

import json
import types

import pytest

from ktdi.features import pseudodoxia
from ktdi.tools import pseudodoxia_build as build
from tests.fakes import Ctx, User, run

SCOTT = User(1, "scott")

VOLUME = """Contents:

  THE FIRST BOOK:

    1. Of the Elephant,                                           308

RELIGIO MEDICI, which has no chapters of Pseudodoxia in it.

                            THE THIRD BOOK

                             CHAPTER I

Of the Elephant.

The first shall be of the Elephant, whereof there generally passeth an opinion it hath no
joints.[12] [SN: _Elephants joints._]

[12] A footnote about elephants.


CHAPTER V

Of the Badger.

That a Brock or Badger hath the legs on one side shorter then of the other, though an
opinion perhaps not very ancient, is yet very general.

Again, It seems no easie affront unto Reason. [Sidenote: _A note
over two lines._]

HYDRIOTAPHIA: URNE BURIAL

CHAPTER I

Of urns, which aren't part of it.

When the Funerall pyre was out.

*** END OF THIS PROJECT GUTENBERG EBOOK
"""


@pytest.fixture(autouse=True)
def chapters(monkeypatch):
    found = build.build({39960: VOLUME}, {"keep": ["3.1", "3.5"]})["chapters"]
    monkeypatch.setattr(pseudodoxia, "DICTIONARY", pseudodoxia.dictionary(found))
    monkeypatch.setattr(pseudodoxia.oldbooks.random, "choice", lambda options: options[0])


# --- Reading the book ---
def test_chapters_are_read_from_the_book():
    found = {c["key"]: c for c in build.chapters(VOLUME, 39960)}
    assert sorted(found) == ["3.1", "3.5"]  # Not the contents, and not Hydriotaphia's chapters
    badger = found["3.5"]
    assert (badger["book"], badger["chapter"], badger["title"]) == (3, 5, "Of the Badger")
    assert badger["text"] == ("That a Brock or Badger hath the legs on one side shorter then of the other, though an "
                              "opinion perhaps not very ancient, is yet very general.\n\nAgain, It seems no easie "
                              "affront unto Reason.")  # Side-notes out, even over two lines
    assert found["3.1"]["text"] == ("The first shall be of the Elephant, whereof there generally passeth an opinion "
                                    "it hath no joints.")  # Footnote mark and footnote out
    assert badger["volume"] == 39960 and badger["anchor"].startswith("That a Brock or Badger hath")


def test_the_real_chapters_are_on_the_allowlist():
    curation = json.loads(build.CURATION.read_text(encoding="utf-8"))
    assert set(curation) == {"_about", "keep"}
    real = json.loads(pseudodoxia.DATA.read_text(encoding="utf-8"))["chapters"]
    assert [c["key"] for c in real] == curation["keep"] and len(real) >= 50
    assert not {"4.10", "6.10", "6.11", "6.12", "6.13"} & set(curation["keep"])  # The racist and antisemitic ones


# --- The command ---
def test_a_topic():
    embed = pseudodoxia.pseudodoxia_embed("badger")
    assert embed.title == "🧐 Of the Badger"
    assert embed.description.startswith("That a Brock or Badger hath the legs on one side shorter")
    assert embed.footer.text == f"{pseudodoxia.SOURCE}, book 3, chapter 5."
    assert embed.url.startswith("https://www.gutenberg.org/cache/epub/39960/pg39960-images.html#:~:text=That%20a")


def test_random_and_nothing():
    assert pseudodoxia.pseudodoxia_embed(None).title == "🧐 Of the Elephant"
    assert "never got round to examining that one" in pseudodoxia.pseudodoxia_embed("zzqx").description


def test_command_and_autocomplete():
    ctx = Ctx(SCOTT)
    run(pseudodoxia.pseudodoxia.callback(ctx, topic="elephants"))
    assert ctx.last.embed.title == "🧐 Of the Elephant"
    assert [c.value for c in run(pseudodoxia.topic_autocomplete(types.SimpleNamespace(), "badg"))] == ["Of the Badger"]
    assert pseudodoxia.pseudodoxia.aliases == ["vulgarerrors", "browne"]
