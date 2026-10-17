"""/talisman: The Book of Talismans, Amulets and Zodiacal Gems (ktdi.features.talisman, ktdi.tools.talisman_build)."""

import json

import pytest

from ktdi.features import lore, talisman
from ktdi.tools import talisman_build as build
from tests.fakes import Ctx, User, run

SCOTT = User(1, "scott")

PAGE = """<html><body><h2 id="CONTENTS">CONTENTS</h2><p>Not the book.</p>
<h2 class="nobreak" id="PART_I">PART I<br>AMULETS AND TALISMANS</h2>
<h3 id="CHAPTER_I">CHAPTER I<br>Introduction</h3>
<blockquote><div><p class="hanging2">The Axe—The Arrow-head</p></div></blockquote>
<p class="drop-cap"><span class="allcap">FROM</span> remotest times talismans<span class="pagenum"
id="Page_3">[3]</span> have been held in high estimation.</p>
<figure class="figcenter"><img src="images/plate_1.jpg"><figcaption><p>PRIMEVAL TALISMANS.</p></figcaption></figure>
<p>The axe, No. 13 (Plate I), was a symbol of power.</p>
<p>The tortoise, No. 36 (Plate III), stood for long life.</p>
<h4>General Talismans</h4>
<p>The four-leaved clover brings luck.</p>
<h2 class="nobreak" id="PART_II">PART II<br>THE GEMS OF THE ZODIAC</h2>
<h3 id="CHAPTER_I_2">CHAPTER I<br>ARIES—THE RAM</h3>
<p>The Sun enters Aries on March 21st.</p>
<p>The diamond is the gem of Aries.</p>
<h2 class="nobreak" id="BIBLIOGRAPHY">BIBLIOGRAPHY</h2><p>Books.</p></body></html>"""

CURATION = {"keep": {
    "1.1.2": {"title": "The Axe", "also": ["axe"]},
    "1.1.3": {"title": "The Tortoise", "also": ["tortoise", "long life"]},
    "1.1.4": {"title": "Four-Leaved Clover", "also": ["clover", "luck"]},
    "2.1.1": {"title": "Aries and the Diamond", "also": ["aries", "diamond"], "to": 2},
}}


@pytest.fixture(autouse=True)
def talismans(monkeypatch):
    found = build.build(PAGE, CURATION)
    assert found["missing"] == []
    monkeypatch.setattr(talisman, "DICTIONARY", talisman.dictionary(found["talismans"]))
    monkeypatch.setattr(talisman.oldbooks.random, "choice", lambda options: options[0])


# --- Reading the book ---
def test_paragraphs_by_part_and_chapter():
    found = build.paragraphs(PAGE)
    assert [p["key"] for p in found] == ["1.1.1", "1.1.2", "1.1.3", "1.1.4", "2.1.1", "2.1.2"]  # A heading in a
    assert found[0]["text"] == "From remotest times talismans have been held in high estimation."  # chapter isn't a
    assert found[0]["where"] == "Talismans and Amulets, Chapter I"  # chapter; contents lists and pictures are out
    assert found[4]["where"] == "Aries—The Ram"


def test_plates_shown_only_when_allowed():
    found = {t["key"]: t for t in build.build(PAGE, CURATION)["talismans"]}
    assert found["1.1.2"]["picture"] is None  # Plate I is never shown
    assert found["1.1.3"]["picture"] == {"url": build.IMAGES + "plate_3.jpg",
                                         "caption": "Plate III: Chinese and Japanese Talismans"}
    assert found["1.1.4"]["picture"] is None
    assert found["2.1.1"]["picture"] == build.FRONTISPIECE  # The zodiac chapters' gems
    assert found["2.1.1"]["text"] == "The Sun enters Aries on March 21st.\n\nThe diamond is the gem of Aries."
    assert {1, 2, 6, 8}.isdisjoint(build.PLATES)


def test_a_sentence_the_book_broke_is_joined():
    assert build.gutenberg.mid_sentence("attached much importance to the", "Eye Amulet, which was first...")
    assert build.gutenberg.mid_sentence("that the Teutonic peoples", "used white horses.")
    assert not build.gutenberg.mid_sentence("the diamond the gem of winter", "For spring, the emerald.")  # A full stop
    assert not build.gutenberg.mid_sentence("these lines:—", "Hang up hooks")  # missing, not a break
    assert not build.gutenberg.mid_sentence("is signified by dreaming of", "Agates — A journey.\nAmber — A voyage.")
    assert not build.gutenberg.mid_sentence("Monday — Pearl\nTuesday — Ruby and", "Fashion in the Orient")


def test_the_curation_is_checked():
    assert build.build(PAGE, {"keep": {"9.9.9": {"title": "Nowhere"}}})["missing"] == ["9.9.9"]


def test_the_real_passages_are_on_the_allowlist():
    curation = json.loads(build.CURATION.read_text(encoding="utf-8"))
    real = json.loads(talisman.DATA.read_text(encoding="utf-8"))["talismans"]
    assert sorted(t["key"] for t in real) == sorted(curation["keep"]) and len(real) >= 100
    assert len({t["title"] for t in real}) == len(real) and all(t["text"] and t["also"] for t in real)
    assert not any("plate_1." in t["picture"]["url"] or "plate_2." in t["picture"]["url"]
                   for t in real if t["picture"])


# --- The command ---
def test_a_talisman_with_its_plate():
    embed = talisman.talismans_embed("tortoise")
    assert embed.title == "🧿 The Tortoise"
    assert embed.image.url.endswith("plate_3.jpg") and embed.fields[0].value.startswith("Plate III")
    assert embed.footer.text == ("W. T. and K. Pavitt, The Book of Talismans, Amulets and Zodiacal Gems (1922): "
                                 "Talismans and Amulets, Chapter I. The Pavitts' beliefs, not checked facts.")
    assert embed.url.startswith("https://www.gutenberg.org/cache/epub/78789/pg78789-images.html#:~:text=The")


def test_a_sign_misspelt_random_and_nothing():
    assert talisman.talismans_embed("aires").title == "🧿 Aries and the Diamond"
    assert not talisman.talismans_embed("axe").fields  # No picture
    assert talisman.talismans_embed(None).title == "🧿 The Axe"
    embed = talisman.talismans_embed("zzqx")
    assert "No talisman for that here" in embed.description and "picked by hand" in embed.description


def test_command_and_autocomplete():  # Autocompleted on its shelf
    ctx = Ctx(SCOTT)
    run(talisman.talisman.callback(ctx, thing="luck"))
    assert ctx.last.embed.title == "🧿 Four-Leaved Clover"
    assert [c.value for c in lore.suggestions("esoteric", "talisman", "four", [talisman.OLD_BOOK])] == ["Four-Leaved Clover"]
    assert talisman.talisman.aliases == ["talismans", "amulet", "zodiac"]
