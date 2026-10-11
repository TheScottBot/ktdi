"""/dream: Miller's Ten Thousand Dreams Interpreted (ktdi.features.dream, ktdi.tools.dream_build)."""

import hashlib
import json
import re
import types
from pathlib import Path

import pytest

from ktdi.features import dream
from ktdi.tools import dream_build as build
from tests.fakes import Ctx, User, run

SCOTT = User(1, "scott")
# SHA-256 fingerprints of the headwords of entries that were taken out, so this can check they stay out without the
# repo spelling any of them out.
LEFT_OUT = set(json.loads((Path(__file__).parent / "dream_left_out.sha256.json").read_text(encoding="utf-8")))

BOOK = """Preface, about the soul.

WHAT'S IN A DREAM.


A.


``_When he was set down on the Judgment seat_.''--Matthew xxvii, 19.

_Abbey_.[3]

To see an abbey in ruins, foretells that your hopes and schemes
will fall into ignoble incompletion.

[3] See similar words in connection with churches, priests, etc.

_Axe_.

Seeing an axe in a dream, foretells that what enjoyment
you may have will depend on your struggles and energy.



B. ``_God came to Abimelech in a dream by night_.''--Gen. xx., 3rd.

_Baby Carriages_.

To dream of a baby carriage, denotes that you will have a congenial
friend who will devise many pleasurable surprises for you.

_Barrel_.[19]

[19] See Cask.

_Cavern or Cave_.

To be in a cave foreshadows change.

_Canary Birds_.  To dream of this sweet songster, denotes
unexpected pleasures.

_Kangaroo_.

To see a kangaroo's hide, denotes that you are in a fair way
to success.  _Katydids_.

To dream of hearing katydids, is a prognostic of misfortune.

_Landlord's Cat_.

For a landlord to see a cat in a dream, denotes he will have business trouble.

_Teeth_.

An ordinary dream of teeth augurs an unpleasant contact with sickness,
or disquieting people.

To have them filled, you will recover lost valuables after much uneasiness.

_Zephyr_.

To dream of a ``gentle zephyr,'' denotes that you will part from a {sic}friend.



INDEX
Abbey . . . 42
"""


@pytest.fixture(autouse=True)
def entries(monkeypatch):
    monkeypatch.setattr(dream, "DICTIONARY", dream.dictionary(build.entries(BOOK)))
    monkeypatch.setattr(dream.random, "choice", lambda options: options[0])


# --- Reading the book ---
def test_the_book_is_split_into_entries():
    found = build.entries(BOOK)
    # Letters' verses, footnotes and the footnote-only Barrel are left out; headings sharing a line are split off.
    assert [e["word"] for e in found] == ["Abbey", "Axe", "Baby Carriages", "Cavern or Cave", "Canary Birds",
                                          "Kangaroo", "Katydids", "Landlord's Cat", "Teeth", "Zephyr"]
    by_word = {e["word"]: e for e in found}
    assert by_word["Abbey"]["text"] == ("To see an abbey in ruins, foretells that your hopes and schemes will fall "
                                        "into ignoble incompletion.")
    assert by_word["Axe"]["text"].endswith("struggles and energy.")  # Not B's verse
    assert by_word["Canary Birds"]["text"] == "To dream of this sweet songster, denotes unexpected pleasures."
    assert by_word["Kangaroo"]["text"] == "To see a kangaroo's hide, denotes that you are in a fair way to success."
    assert by_word["Teeth"]["text"].count("\n\n") == 1  # Two paragraphs
    assert by_word["Zephyr"]["text"] == "To dream of a “gentle zephyr,” denotes that you will part from a friend."


def test_what_was_taken_out_stays_out():
    real = json.loads(dream.DATA.read_text(encoding="utf-8"))["entries"]
    assert len(LEFT_OUT) >= 50
    for entry in real:
        assert hashlib.sha256(entry["word"].encode("utf-8")).hexdigest() not in LEFT_OUT, entry["word"]


def test_the_real_book_is_exactly_whats_on_the_allowlist():
    curation = json.loads(build.gutenberg.curation_file("dream").read_text(encoding="utf-8"))
    assert set(curation) == {"_about", "keep"}  # Nothing records what was taken out.
    real = json.loads(dream.DATA.read_text(encoding="utf-8"))["entries"]
    assert len(real) >= 2000
    assert [e["word"] for e in real] == curation["keep"]
    for entry in real:
        assert entry["word"].strip() and entry["text"].strip(), entry
        assert "``" not in entry["text"] and not re.search(r"\[\d+\]", entry["text"]), entry["word"]  # Tidied
        assert "#:~:text=" in dream.url(entry), entry["word"]


# --- Interpreting ---
def test_a_thing_by_name():
    for typed in ["teeth", "Teeth", "teeht"]:
        assert dream.interpret(typed).title == "🔮 Teeth", typed
    embed = dream.interpret("teeth")
    assert embed.description == (
        "An ordinary dream of teeth augurs an unpleasant contact with sickness, or disquieting people.\n\n"
        "To have them filled, you will recover lost valuables after much uneasiness.\n\n"
        "-# 🔮 The committee accepts no liability for prophecies.")
    assert embed.footer.text == dream.SOURCE
    assert embed.url == ("https://www.gutenberg.org/cache/epub/926/pg926-images.html#:~:text="
                         "An%20ordinary%20dream%20of%20teeth%20augurs%20an%20unpleasant%20contact%20with")


def test_the_whole_dream():
    assert dream.interpret("I dreamt all my teeth fell out").title == "🔮 Teeth"
    assert dream.interpret("last night I was lost in a cave").title == "🔮 Cavern or Cave"
    assert dream.interpret("there were baby carriages everywhere").title == "🔮 Baby Carriages"


def test_dreams_that_mention_it():
    embed = dream.interpret("business trouble")
    assert embed.title == "🔮 Dreams that mention “business trouble”"
    assert embed.description == (
        "**[Landlord's Cat](https://www.gutenberg.org/cache/epub/926/pg926-images.html#:~:text="
        "For%20a%20landlord%20to%20see%20a%20cat%20in%20a%20dream)**: "
        "For a landlord to see a cat in a dream, denotes he will have business trouble.")
    assert embed.url is None  # Not the book's front page: each dream links to its own place


def test_nothing_found():
    assert "Miller had nothing on that" in dream.interpret("zzqx").description


def test_random():
    assert dream.interpret(None).title == "🔮 Abbey"
    assert dream.interpret("  ").title == "🔮 Abbey"


def test_command_and_autocomplete():
    ctx = Ctx(SCOTT)
    run(dream.dream.callback(ctx))
    assert ctx.last.embed.title == "🔮 Abbey"
    run(dream.dream.callback(ctx, thing="eek a kangaroo"))
    assert ctx.last.embed.title == "🔮 Kangaroo"
    choices = run(dream.thing_autocomplete(types.SimpleNamespace(), "ca"))
    assert [c.value for c in choices] == ["Canary Birds", "Cave", "Cavern", "Baby Carriages", "Landlord's Cat"]
