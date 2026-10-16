"""/gemlore: The Curious Lore of Precious Stones (ktdi.features.gem, ktdi.tools.gem_build)."""

import json
import types

import pytest

from ktdi.features import gem
from ktdi.tools import gem_build as build
from ktdi.tools import gutenberg
from tests.fakes import Ctx, User, run

SCOTT = User(1, "scott")

PAGE = """<html><body><h2>Contents</h2><p>Not the book.</p>
<h2><a id="I">I</a><br><small>Superstitions and Their Sources</small></h2>
<p class="drop-cap first-letter">FROM the earliest times gems<a class="fnanchor pginternal" href="#Footnote_1_1"
id="FNanchor_1_1">1</a> have been held in great esteem.<span class="pagenum" id="Page_2">2</span></p>
<div class="figcenter" role="figure"><a id="img1"></a><img alt="" src="images/i_010fpa.jpg">
<div class="caption" id="ebm_caption1">ROCK-CRYSTAL AMULET SET IN SILVER.<br><small>Bohemian, tenth century.</small></div>
</div>
<p><span class="pagenum" id="Page_3">3</span></p>
<p>The magi found much in gems.</p>
<h2><a id="III">III</a><br><small>On the Talismanic Use of Special Stones</small></h2>
<h3>Agate</h3>
<p>THE author of <i>Lithica</i> celebrates the agate.</p>
<div class="figcenter"><a id="img2"></a><img alt="" src="images/i_020fp.jpg"></div>
<ul class="small"><li>1. Eye agates, Arabia.</li><li>2. Antique eye agates.</li></ul>
<div class="poetry-container"><div class="poetry"><div class="stanza"><div class="verse">Adorned with this,</div>
<div class="verse">thy desire obtain.</div></div></div></div>
<h2><a id="VII">VII</a><br></h2>
<h3>Religious Uses of Precious Stones.</h3>
<div class="figcenter"><img alt="" src="images/i_077thumb.jpg"><div class="captionl"><p class="center">A PAGE.</p>
<p class="limage">A larger image is available <a href="images/i_077.jpg">here</a>.</p></div></div>
<p>The Sacro Catino of Genoa was green glass.</p>
<h2><a id="IX">IX</a><br><small>Birth-Stones</small></h2>
<h3>SENTIMENTS OF THE MONTHS</h3>
<h4>JANUARY</h4>
<p>No gems save garnets should be worn.</p>
<h2><a id="XI">XI</a><br><small>On the Therapeutic Use of Precious Stones</small></h2>
<p>A cure, not kept.</p>
<h2>Index</h2></body></html>"""

CURATION = {"keep": {
    "2.1.1": {"title": "Agate in Verse", "also": ["agate", "lithica"], "to": 2, "picture": "i_020fp"},
    "3.1.1": {"title": "The Sacro Catino", "also": ["emerald", "genoa"]},
    "4.2.1": {"title": "January's Stones", "also": ["garnet", "january"]},
}}


@pytest.fixture(autouse=True)
def gems(monkeypatch):
    found = build.build(PAGE, CURATION)
    assert found["missing"] == []
    monkeypatch.setattr(gem, "DICTIONARY", gem.dictionary(found["gems"]))
    monkeypatch.setattr(gem.oldbooks.random, "choice", lambda options: options[0])


# --- Reading the book ---
def test_paragraphs_are_read_without_pictures_footnotes_or_the_medicine():
    found = build.paragraphs(PAGE)
    assert [p["key"] for p in found] == ["1.0.1", "1.0.2", "2.1.1", "2.1.2", "3.1.1", "4.2.1"]  # Counted in order; no chapter XI
    assert found[0]["text"] == "From the earliest times gems have been held in great esteem."  # Drop cap, marks out
    assert found[0]["where"] == "Superstitions and Their Sources"
    assert found[2]["where"] == "On the Talismanic Use of Special Stones: Agate"
    assert found[3]["text"] == "Adorned with this,\nthy desire obtain."  # Not the list captioning the picture
    assert found[4]["where"] == "Religious Uses of Precious Stones"  # Chapter VII is named by its one section
    assert found[5]["where"] == "Birth-Stones: January"


def test_pictures_and_their_captions():
    found = build.pictures(PAGE)
    assert found["i_010fpa"] == {"url": build.IMAGES + "images/i_010fpa.jpg",
                                 "caption": "Rock-Crystal Amulet Set in Silver\nBohemian, tenth century."}
    assert found["i_020fp"]["caption"] == "1. Eye agates, Arabia.\n2. Antique eye agates."  # The list after it
    assert found["i_077"] == {"url": build.IMAGES + "images/i_077.jpg", "caption": "A Page"}  # The larger image


def test_a_run_a_picture_and_the_curation_checked():
    agate = build.build(PAGE, CURATION)["gems"][0]
    assert agate["text"] == "The author of _Lithica_ celebrates the agate.\n\nAdorned with this,\nthy desire obtain."
    assert agate["picture"]["url"].endswith("i_020fp.jpg") and agate["also"] == ["agate", "lithica"]
    found = build.build(PAGE, {"keep": {"9.9.9": {"title": "Nowhere"}, "1.0.1": {"title": "X", "picture": "i_999"}}})
    assert found["missing"] == ["9.9.9", "1.0.1's picture i_999"]


def test_headed_paragraphs_count_sections_in_each_chapter():
    found = gutenberg.headed_paragraphs("<h2>One</h2><p>Intro.</p><h3>A</h3><p>a.</p><h2>Two</h2><h4>B</h4><p>b.</p>")
    assert [(p["key"], p["section_title"]) for p in found] == [("1.0.1", ""), ("1.1.1", "A"), ("2.1.1", "B")]


def test_the_real_passages_are_on_the_allowlist():
    curation = json.loads(build.CURATION.read_text(encoding="utf-8"))
    real = json.loads(gem.DATA.read_text(encoding="utf-8"))["gems"]
    assert sorted(g["key"] for g in real) == sorted(curation["keep"]) and len(real) >= 100
    assert len({g["title"] for g in real}) == len(real) and all(g["text"] and g["also"] for g in real)
    assert not any(g["key"].startswith("11.") for g in real)


# --- The command ---
def test_a_stone():
    embed = gem.gems_embed("agate")
    assert embed.title == "💎 Agate in Verse"
    assert embed.image.url.endswith("i_020fp.jpg")
    assert embed.fields[0].name == "In the picture" and embed.fields[0].value.startswith("1. Eye agates")
    assert embed.footer.text == ("George Frederick Kunz, The Curious Lore of Precious Stones (1913): On the Talismanic "
                                 "Use of Special Stones: Agate. His account of old beliefs: some of the attributions "
                                 "are disputed.")
    assert embed.url.startswith("https://www.gutenberg.org/cache/epub/57978/pg57978-images.html#:~:text=The")


def test_a_month_misspelt_random_and_nothing():
    assert gem.gems_embed("januray").title == "💎 January's Stones"
    assert not gem.gems_embed("genoa").fields  # No picture, no caption
    assert gem.gems_embed(None).title == "💎 Agate in Verse"
    embed = gem.gems_embed("zzqx")
    assert "Nothing on that stone here" in embed.description and "picked by hand" in embed.description


def test_command_and_autocomplete():
    ctx = Ctx(SCOTT)
    run(gem.gemlore.callback(ctx, stone="garnet"))
    assert ctx.last.embed.title == "💎 January's Stones"
    assert [c.value for c in run(gem.stone_autocomplete(types.SimpleNamespace(), "sacro"))] == ["The Sacro Catino"]
    assert gem.gemlore.aliases == ["gems", "birthstone"]
