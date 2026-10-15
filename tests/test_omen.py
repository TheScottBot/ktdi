"""/omen: The Magic of the Horse-shoe (ktdi.features.omen, ktdi.tools.omen_build)."""

import json
import types

import pytest

from ktdi.features import omen
from ktdi.tools import omen_build as build
from tests.fakes import Ctx, User, run

SCOTT = User(1, "scott")

PAGE = """<html><body><h2>CONTENTS</h2><p>Not the book.</p>
<h2 id="THE_MAGIC_OF_THE_HORSE-SHOE">THE MAGIC OF THE HORSE-SHOE</h2>
<p>A motto, not a passage.</p>
<h3>I. HISTORY OF THE HORSE-SHOE</h3>
<p>The evolution of the modern horse-shoe<a class="fnanchor pginternal" href="#Footnote_1">[1]</a> is a
<i>curious</i> subject.</p>
<p>A second paragraph.</p>
<h2 id="THE_FOLK-LORE_OF_COMMON_SALT">THE FOLK-LORE OF COMMON SALT<a class="fnanchor" href="#Footnote_2">[252]</a></h2>
<h3>V. SALT-SPILLING AS AN OMEN</h3>
<p>The widespread notion that the spilling of salt produces evil consequences is very old.</p>
<p>To avert the ill luck, a pinch is thrown over the left shoulder.</p>
<p>And so the Devil is blinded.</p>
<h2>FOOTNOTES</h2><p>[1] A footnote.</p></body></html>"""

CURATION = {"keep": {
    "1.1.1": {"title": "The First Horseshoes", "also": ["horseshoe"]},
    "2.5.1": {"title": "Spilling Salt", "also": ["salt", "bad luck"], "to": 2},
}}


@pytest.fixture(autouse=True)
def omens(monkeypatch):
    found = build.build(PAGE, CURATION)
    assert found["missing"] == []
    monkeypatch.setattr(omen, "DICTIONARY", omen.dictionary(found["omens"]))
    monkeypatch.setattr(omen.oldbooks.random, "choice", lambda options: options[0])


# --- Reading the book ---
def test_paragraphs_are_read_from_the_page():
    found = build.paragraphs(PAGE)
    assert [p["key"] for p in found] == ["1.1.1", "1.1.2", "2.5.1", "2.5.2", "2.5.3"]  # No mottoes, no footnotes
    first, _, salt, *_ = found
    assert first["text"] == "The evolution of the modern horse-shoe is a _curious_ subject."  # Footnote mark out
    assert (salt["essay_title"], salt["section"], salt["section_title"]) == \
        ("The Folk-Lore of Common Salt", 5, "Salt-Spilling as an Omen")


def test_a_run_of_paragraphs_and_the_curation_checked():
    salt = next(o for o in build.build(PAGE, CURATION)["omens"] if o["key"] == "2.5.1")
    assert salt["text"] == ("The widespread notion that the spilling of salt produces evil consequences is very old.\n\n"
                            "To avert the ill luck, a pinch is thrown over the left shoulder.")
    found = build.build(PAGE, {"keep": {"2.5.2": {"title": "Over the Shoulder", "to": 9},
                                        "9.9.9": {"title": "Nowhere"}}})
    assert found["missing"] == ["9.9.9", "2.5.2 to 9"]


def test_the_real_omens_are_on_the_allowlist():
    curation = json.loads(build.CURATION.read_text(encoding="utf-8"))
    real = json.loads(omen.DATA.read_text(encoding="utf-8"))["omens"]
    assert sorted(o["key"] for o in real) == sorted(curation["keep"]) and len(real) >= 60
    assert len({o["title"] for o in real}) == len(real) and all(o["text"] for o in real)


# --- The command ---
def test_an_omen():
    embed = omen.omens_embed("salt")
    assert embed.title == "🍀 Spilling Salt"
    assert embed.description.endswith("a pinch is thrown over the left shoulder.")
    assert embed.footer.text == ("Robert Means Lawrence, The Magic of the Horse-shoe (1898): The Folk-Lore of Common "
                                 "Salt, Salt-Spilling as an Omen.")
    assert embed.url.startswith("https://www.gutenberg.org/cache/epub/57411/pg57411-images.html#:~:text=The")


def test_misspelt_random_and_nothing():
    assert omen.omens_embed("horsehoe").title == "🍀 The First Horseshoes"
    assert omen.omens_embed(None).title == "🍀 The First Horseshoes"
    embed = omen.omens_embed("zzqx")
    assert "No omen about that here" in embed.description and "picked by hand" in embed.description


def test_command_and_autocomplete():
    ctx = Ctx(SCOTT)
    run(omen.omen.callback(ctx, what="bad luck"))
    assert ctx.last.embed.title == "🍀 Spilling Salt"
    assert [c.value for c in run(omen.what_autocomplete(types.SimpleNamespace(), "spill"))] == ["Spilling Salt"]
    assert omen.omen.aliases == ["omens", "superstition"]
