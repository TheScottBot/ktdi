"""/flowermeaning: The Language of Flowers (ktdi.features.flower, ktdi.tools.flower_build)."""

import json
import types

import pytest

from ktdi.features import flower
from ktdi.tools import flower_build as build
from tests.fakes import Ctx, User, run

SCOTT = User(1, "scott")

PAGE = """<html><body><h2><a id="Preface"></a>Preface.</h2><p>Not a flower.</p>
<h2><a id="Pansy_Think_of_me"></a><span class="smcap">Pansy</span>.... <i>Think of me</i>.</h2>
<p><span class="smcap">The</span> Pansy, or Heart’s-ease, is a beautiful variety
of the Violet.</p>
<div class="poetry"><div class="poem"><div class="stanza">
<span class="i0">“And there are Pansies, that’s for thoughts.”<br></span></div></div></div>
<div class="figcenter"><img alt="SWEET PEA PANSY  I depart. Think on me." src="images/i_207.jpg"></div>
<h2><a id="Sweet_Brier"></a><span class="smcap">Sweet-Brier, or Eglantine</span>. ... <i>Poetry</i>.</h2>
<p>A wild rose.</p>
<h2><a id="Death"></a>DEATH OF THE FLOWERS.</h2><p>Not a flower either.</p>
<h2><a id="Dictionary_of_Flowers"></a>Dictionary of Flowers,<br><br><small>WITH THEIR SIGNIFICATIONS.</small></h2>
<table><tbody><tr><td>Acacia</td><td>Friendship.</td></tr>
<tr><td>—— Rose</td><td>Elegance.</td></tr>
<tr><td>Basil</td><td>Hate.</td></tr>
<tr><td>Myrtle</td><td>Love.</td></tr>
<tr><td>Pansy</td><td>Thoughts.</td></tr>
<tr><td>——</td><td>Think of me.</td></tr>
<tr><td>Rose</td><td>Love.</td></tr>
<tr><td>Rose, Moss</td><td>Confession of Love.</td></tr>
</tbody></table></body></html>"""

CURATION = {"keep": ["Acacia", "Acacia, Rose", "Basil", "Myrtle", "Pansy", "Rose", "Rose, Moss", "Sweet-Brier"],
            "no_text": ["Sweet-Brier"]}


@pytest.fixture(autouse=True)
def flowers(monkeypatch):
    found = build.build(PAGE, CURATION)
    assert found["missing"] == []
    monkeypatch.setattr(flower, "DICTIONARY", flower.dictionary(found["flowers"]))
    monkeypatch.setattr(flower.random, "choice", lambda options: options[0])
    monkeypatch.setattr(flower.random, "sample", lambda options, n: list(options)[:n])


# --- Reading the book ---
def test_the_dictionary_and_its_dashes():
    assert build.dictionary(PAGE)[:2] == [("Acacia", "Friendship"), ("Acacia, Rose", "Elegance")]
    assert ("Pansy", "Think of me") in build.dictionary(PAGE)  # "——" alone: the same flower again


def test_chapters_join_the_dictionary():
    found = {f["name"]: f for f in build.flowers(PAGE)}
    pansy = found["Pansy"]
    assert pansy["meanings"] == ["Thoughts", "Think of me"]  # The chapter's meaning is the dictionary's second
    assert pansy["text"] == ("The Pansy, or Heart’s-ease, is a beautiful variety of the Violet.\n\n"
                             "“And there are Pansies, that’s for thoughts.”")  # Not the plate's caption
    assert pansy["anchor"] == "Pansy_Think_of_me"
    assert pansy["plate"]["message"] == "I depart. Think on me."
    assert found["Sweet-Brier"]["also"] == ["Eglantine"] and found["Sweet-Brier"]["meanings"] == ["Poetry"]
    assert found["Basil"]["text"] is None and found["Basil"]["anchor"] == "Dictionary_of_Flowers"
    assert "Death of the Flowers" not in found and "Preface" not in found
    assert found["Rose, Moss"]["plate"]  # "Moss Rose" in the plate is the dictionary's "Rose, Moss"


def test_the_curation():
    kept = {f["name"]: f for f in build.build(PAGE, CURATION)["flowers"]}
    assert kept["Sweet-Brier"]["text"] is None  # Its chapter was left out; its meaning wasn't
    assert build.build(PAGE, {"keep": ["Basil", "Daffodil"]})["missing"] == ["Daffodil"]


def test_the_real_flowers_are_on_the_allowlist():
    curation = json.loads(build.CURATION.read_text(encoding="utf-8"))
    real = json.loads(flower.DATA.read_text(encoding="utf-8"))["flowers"]
    assert sorted(f["name"] for f in real) == sorted(curation["keep"]) and len(real) >= 200
    assert all(f["meanings"] for f in real)
    assert not any(f["text"] for f in real if f["name"] in curation["no_text"])


# --- The command ---
def test_a_flower_with_its_chapter_and_plate():
    embed = flower.flowermeaning_embed("pansy")
    assert embed.title == "🌸 Pansy"
    assert embed.description.startswith("**Thoughts · Think of me**\n\nThe Pansy, or Heart’s-ease")
    assert embed.url == f"{flower.PAGE}#Pansy_Think_of_me"
    assert embed.image.url.endswith("images/i_207.jpg")
    assert embed.fields[0].name == "In a bouquet: Sweet Pea, Pansy" and embed.fields[0].value == "*I depart. Think on me.*"
    assert embed.footer.text == ("Henrietta Dumont, The Language of Flowers (1851). Her meanings: other books of the "
                                 "day give others.")


def test_a_meaning_finds_the_flowers():
    embed = flower.flowermeaning_embed("love")
    assert embed.title == "🌸 Myrtle"
    assert embed.fields[-1].name == "Also meaning “love”" and embed.fields[-1].value == "Rose · Rose, Moss"


def test_another_name_misspelt_random_and_nothing():
    assert flower.flowermeaning_embed("eglantine").title == "🌸 Sweet-Brier"
    assert flower.flowermeaning_embed("bassil").title == "🌸 Basil"
    assert flower.flowermeaning_embed(None).title == "🌸 Acacia"
    assert "No flower for that here" in flower.flowermeaning_embed("zzqx").description


def test_command_and_autocomplete():
    ctx = Ctx(SCOTT)
    run(flower.flowermeaning.callback(ctx, flower="basil"))
    assert ctx.last.embed.title == "🌸 Basil" and ctx.last.embed.description == "**Hate**"
    assert [c.value for c in run(flower.flower_autocomplete(types.SimpleNamespace(), "bas"))] == ["Basil"]
    assert flower.flowermeaning.aliases == ["flower", "floriography"]
