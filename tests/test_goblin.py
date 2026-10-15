"""/goblin: Wirt Sikes's British Goblins (ktdi.features.goblin, ktdi.tools.goblin_build)."""

import json
import types

import pytest

from ktdi.features import goblin
from ktdi.tools import goblin_build as build
from tests.fakes import Ctx, User, run

SCOTT = User(1, "scott")

PAGE = """<html><body><h1>BRITISH GOBLINS</h1>
<h2 class="padtop"><a id="book1"></a><span class="lrgfont">BOOK I.</span><br> <br>
<span class="smlfont">THE REALM OF FAERIE.</span></h2>
<h3 class="padtop"><a id="bk1chap01"></a>CHAPTER I.</h3>
<div class="blockquot"><p class="hang">Fairy Tales and the Ancient Mythology—Rowli Pugh and the Ellyll.</p></div>
<h4>I.</h4>
<p>With regard to other divisions of the field of folk-lore,<a id="FNanchor_1_1"></a><a class="fnanchor pginternal"
href="#Footnote_1_1">[1]</a> the views of <i>scholars</i> differ.</p>
<div class="footnotes"><p class="center">FOOTNOTE:</p><div class="footnote"><p>[1] ‘Saturday Review.’</p></div></div>
<h4>II.</h4>
<p>Rowli Pugh was a farmer, and bad luck plagued him.</p>
<div class="figcenter imgw1"><img alt="Rowli talks to the fairy" src="images/bg04.jpg" width="375"></div>
<p class="caption">ROWLI AND THE ELLYLL.</p>
<p>His bad luck never returned.</p>
<div class="figcenter"><img alt="Music notation, untitled" src="images/bgm01.png"></div>
<h2 class="padtop"><a id="book2"></a><span class="lrgfont">BOOK II.</span><br> <br>
<span class="smlfont">THE SPIRIT-WORLD.</span></h2>
<h3><a id="bk2chap01"></a>CHAPTER I.</h3>
<div class="blockquot"><p class="hang">The Corpse Candle—The Cyhyraeth.</p></div>
<h4>I.</h4>
<p>The corpse candle is a small light that goes before a funeral.</p>
<h2><a id="index"></a>INDEX</h2></body></html>"""

CURATION = {"keep": {
    "1.1.2": {"title": "Rowli Pugh and the Ellyll", "also": ["Ellyll", "Elf"]},
    "2.1.1": {"title": "The Corpse Candle", "also": ["Canwyll Corph"]},
}}


@pytest.fixture(autouse=True)
def tales(monkeypatch):
    found = build.build(PAGE, CURATION)
    assert found["missing"] == []
    monkeypatch.setattr(goblin, "DICTIONARY", goblin.dictionary(found["tales"]))
    monkeypatch.setattr(goblin.oldbooks.random, "choice", lambda options: options[0])


# --- Reading the book ---
def test_sections_are_read_from_the_page():
    first, rowli, candle = build.sections(PAGE)
    assert [s["key"] for s in (first, rowli, candle)] == ["1.1.1", "1.1.2", "2.1.1"]
    assert (rowli["book_title"], candle["book_title"]) == ("The Realm of Faerie", "The Spirit-World")
    assert rowli["topics"] == ["Fairy Tales and the Ancient Mythology", "Rowli Pugh and the Ellyll"]
    assert first["text"] == "With regard to other divisions of the field of folk-lore, the views of _scholars_ differ."
    assert rowli["text"] == "Rowli Pugh was a farmer, and bad luck plagued him.\n\nHis bad luck never returned."
    assert rowli["images"] == [{"url": f"{build.IMAGES}images/bg04.jpg", "caption": "Rowli and the Ellyll"}]


def test_the_curation_is_checked_against_the_book():
    found = build.build(PAGE, {"keep": {"1.1.2": {"title": "Rowli"}, "9.9.9": {"title": "Nowhere"}}})
    assert [t["key"] for t in found["tales"]] == ["1.1.2"] and found["missing"] == ["9.9.9"]
    assert found["tales"][0]["also"] == []


def test_the_real_tales_are_on_the_allowlist():
    curation = json.loads(build.CURATION.read_text(encoding="utf-8"))
    real = json.loads(goblin.DATA.read_text(encoding="utf-8"))["tales"]
    assert sorted(t["key"] for t in real) == sorted(curation["keep"]) and len(real) >= 60
    assert len({t["title"] for t in real}) == len(real)  # Every title is its own
    assert all(t["text"] and t["title"] for t in real)


# --- The command ---
def test_a_tale_with_its_picture():
    embed = goblin.goblin_embed("ellyll")
    assert embed.title == "🧚 Rowli Pugh and the Ellyll"
    assert embed.description == "Rowli Pugh was a farmer, and bad luck plagued him.\n\nHis bad luck never returned."
    assert embed.image.url == f"{build.IMAGES}images/bg04.jpg"
    assert embed.footer.text == "Wirt Sikes, British Goblins (1880): The Realm of Faerie."
    assert embed.url.startswith("https://www.gutenberg.org/cache/epub/34704/pg34704-images.html#:~:text=Rowli")


def test_other_names_misspellings_random_and_nothing():
    assert goblin.goblin_embed("canwyll corph").title == "🧚 The Corpse Candle"
    assert goblin.goblin_embed("corpse candel").title == "🧚 The Corpse Candle"
    assert goblin.goblin_embed(None).title == "🧚 Rowli Pugh and the Ellyll"
    assert "Sikes heard no tale of that in all Wales" in goblin.goblin_embed("zzqx").description


def test_command_and_autocomplete():
    ctx = Ctx(SCOTT)
    run(goblin.goblin.callback(ctx, what="corpse candle"))
    assert ctx.last.embed.title == "🧚 The Corpse Candle" and not ctx.last.embed.image.url
    assert [c.value for c in run(goblin.what_autocomplete(types.SimpleNamespace(), "rowli"))] == \
        ["Rowli Pugh and the Ellyll"]
    assert goblin.goblin.aliases == ["goblins", "fairies"]
