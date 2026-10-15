"""/wonder: Ten Thousand Wonderful Things (ktdi.features.wonder, ktdi.tools.wonder_build)."""

import json
import types

import pytest

from ktdi.features import wonder
from ktdi.tools import wonder_build as build
from tests.fakes import Ctx, User, run

SCOTT = User(1, "scott")

PAGE = f"""<html><body><p class="center">INDEX.</p><p>Not the book yet.</p>
<p class="center">{build.FIRST}</p>
<div class="figcenter"><img alt="" src="images/i_018.jpg" width="500"></div>
<p>The instruments most in vogue
with our ancestors were three.<span class="pagenum"><a id="Page_2">[Pg 2]</a></span></p>
<p class="center">FOX KILLED BY A SWAN.</p>
<p>At Peusey, a swan sitting on her eggs observed a <i>fox</i> swimming towards her.</p>
<div class="poem"><div class="stanza"><span class="i0">"Here lies the fox,<br></span>
<span class="i0">Who met a swan."<br></span></div></div>
<p class="center">HENRY VIII.'S WALKING STICK.</p>
<div class="image-left"><img alt="Henry VIII.'s Walking Stick" src="images/i_030.jpg"></div>
<div class="figcenter"><img alt="Horizontal line" src="images/i_006.jpg"></div>
<p>King Henry VIII. walking one night<br>round the city.</p>
<p class="center">FOX KILLED BY A SWAN.</p>
<p>Another fox, another swan.</p>
<p class="center">1844.</p><p>Not a title: a year, centred.</p>
  PRINTED BY WILLIAM CLOWES AND SONS</body></html>"""

CURATION = {"keep": ["FOX KILLED BY A SWAN.", "HENRY VIII.'S WALKING STICK.", "FOX KILLED BY A SWAN. (2)"]}


@pytest.fixture(autouse=True)
def wonders(monkeypatch):
    found = build.build(PAGE, CURATION)
    assert found["missing"] == []
    monkeypatch.setattr(wonder, "DICTIONARY", wonder.dictionary(found["wonders"]))
    monkeypatch.setattr(wonder.oldbooks.random, "choice", lambda options: options[0])


# --- Reading the book ---
def test_articles_are_read_from_the_page():
    found = build.articles(PAGE)
    assert [(a["number"], a["key"]) for a in found] == [
        (1, build.FIRST), (2, "FOX KILLED BY A SWAN."), (3, "HENRY VIII.'S WALKING STICK."),
        (4, "FOX KILLED BY A SWAN. (2)")]  # The index isn't one, nor is a centred year; a title used twice is told apart
    first, fox, stick, _ = found
    assert first["text"] == "The instruments most in vogue with our ancestors were three."  # Page number out
    assert fox["text"] == ('At Peusey, a swan sitting on her eggs observed a _fox_ swimming towards her.\n\n'
                           '"Here lies the fox,\nWho met a swan."')  # Italics kept, verse on its lines
    assert stick["text"] == "King Henry VIII. walking one night\nround the city."
    assert stick["images"] == [{"url": f"{build.IMAGES}images/i_030.jpg", "caption": "Henry VIII.'s Walking Stick"}]
    assert first["images"][0]["url"].endswith("images/i_018.jpg")  # Not the decorative line


def test_titles():
    assert build.gutenberg.titled("FOX KILLED BY A SWAN.") == "Fox Killed by a Swan"
    assert build.gutenberg.titled("HENRY VIII.'S WALKING STICK.") == "Henry VIII.'s Walking Stick"
    assert build.gutenberg.titled("THE FIRST HERMITS—WHY SO-CALLED.") == "The First Hermits—Why So-Called"
    assert build.gutenberg.titled("DR. JOHNSON'S HOUSE") == "Dr. Johnson's House"
    assert build.gutenberg.titled("CIVIL WAR AND LOUIS XIV.") == "Civil War and Louis XIV"  # CIVIL isn't a numeral


def test_the_curation_is_checked_against_the_book():
    found = build.build(PAGE, {"keep": ["FOX KILLED BY A SWAN.", "A LUCKY FIND."]})
    assert [w["key"] for w in found["wonders"]] == ["FOX KILLED BY A SWAN."]
    assert found["missing"] == ["A LUCKY FIND."]


def test_the_real_wonders_are_on_the_allowlist():
    curation = json.loads(build.CURATION.read_text(encoding="utf-8"))
    real = json.loads(wonder.DATA.read_text(encoding="utf-8"))["wonders"]
    assert sorted(w["key"] for w in real) == sorted(curation["keep"]) and len(real) >= 200
    assert [w["number"] for w in real] == sorted(w["number"] for w in real)  # Book order
    assert all(w["text"] and w["title"] for w in real)


# --- The command ---
def test_a_wonder_with_its_picture():
    embed = wonder.wonders_embed("walking stick")
    assert embed.title == "✨ Henry VIII.'s Walking Stick"
    assert embed.description == "King Henry VIII. walking one night\nround the city."
    assert embed.image.url == f"{build.IMAGES}images/i_030.jpg"
    assert embed.footer.text == ("Wonder No. 3, from Ten Thousand Wonderful Things (1894). The book's claims, not "
                                 "checked facts.")
    assert embed.url.startswith("https://www.gutenberg.org/cache/epub/45849/pg45849-images.html#:~:text=King")


def test_more_than_one_and_no_picture():
    embed = wonder.wonders_embed("swan")
    assert embed.title == "✨ Fox Killed by a Swan" and not embed.image.url
    assert embed.footer.text.endswith("The cabinet has more on that: ask again (2 wonders).")


def test_random_and_nothing():
    assert wonder.wonders_embed(None).title == "✨ Fox Killed by a Swan"
    assert "Nothing on that in this cabinet" in wonder.wonders_embed("zzqx").description


def test_command_and_autocomplete():
    ctx = Ctx(SCOTT)
    run(wonder.wonder.callback(ctx, topic="walking stick"))
    assert ctx.last.embed.title == "✨ Henry VIII.'s Walking Stick"
    assert [c.value for c in run(wonder.topic_autocomplete(types.SimpleNamespace(), "henry"))] == \
        ["Henry VIII.'s Walking Stick"]
    assert wonder.wonder.aliases == ["wonders", "curiosity"]
