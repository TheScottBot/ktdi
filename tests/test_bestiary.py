"""/bestiary: Topsell's beasts and serpents (ktdi.features.bestiary, ktdi.tools.bestiary_build; reading the
books is tests/test_tcp.py)."""

import json

import pytest

from ktdi.features import bestiary, lore
from ktdi.tools import bestiary_build as build, tcp
from tests.fakes import Ctx, User, run

SCOTT = User(1, "scott")

BOOK = """<TEI xmlns="http://www.tei-c.org/ns/1.0"><text>
<front><pb facs="tcp:1:1"/><pb facs="tcp:1:1"/><p>The title page.</p></front>
<body>
<div type="part"><head>OF THE <hi>VNICORNE.</hi></head>
<pb n="711" facs="tcp:1:2"/>
<p><seg rend="decorInit">W</seg>E are now come to the hiſtory of a beaſt<note place="margin">Plin.</note>, whereof
diuers people haue made great queſtion, fro<g ref="char:cmbAbbrStroke">̄</g> the <hi>Indians</hi> to vs.</p>
<p><figure><head>The figure of the Vnicorne.</head></figure>His horne is ſoueraigne, as <gap reason="illegible"
extent="1 word"><desc>(1 word)</desc></gap> writeth:</p>
<q><l>Not part of the paragraph,</l></q>
<p>
<pb n="712" facs="tcp:1:2"/>Of the Vnicorne thus the Poet: <q><l>A horne he hath,</l><l>and ſo he goes.</l></q>
And there an end.</p>
<div type="subpart"><head>OF THE SEA-<lb/>VNICORNE.</head>
<p>AMong the fiſhes there is one.</p>
</div>
</div>
</body></text></TEI>"""

CURATION = {"keep": {
    "beasts:0": {"head": "OF THE VNICORNE", "name": "Unicorn", "also": ["Monoceros"], "paragraphs": [0, 2]},
    "beasts:1": {"head": "OF THE SEA-VNICORNE", "name": "Sea-unicorn", "paragraphs": [0]},
}}


@pytest.fixture(autouse=True)
def passages(monkeypatch):
    found = tcp.kept({"beasts": BOOK}, CURATION, {"beasts": ["", "it is a beast of great question"]})
    monkeypatch.setattr(bestiary, "DICTIONARY", bestiary.dictionary(found["passages"]))
    monkeypatch.setattr(bestiary.oldbooks.random, "choice", lambda options: options[0])


def test_the_real_passages_are_on_the_allowlist():
    curation = json.loads(build.CURATION.read_text(encoding="utf-8"))
    real = json.loads(bestiary.DATA.read_text(encoding="utf-8"))["passages"]
    numbers = [(key, n["number"] if isinstance(n, dict) else n) for key, kept in curation["keep"].items()
               for n in kept["paragraphs"]]
    assert [p["key"] for p in real] == [f"{key}:{n}" for key, n in numbers]
    assert len(real) >= 300 and all(p["text"] and p["name"] for p in real)


# --- The command ---
def test_a_beast():
    embed = bestiary.bestiary_embed("unicorns")
    assert embed.title == "🐉 Unicorn"
    assert embed.description.startswith("We are now come to the history of a beast")
    assert "*Indians*" in embed.description  # Italics kept
    assert embed.footer.text == ('Edward Topsell, The Historie of Foure-footed Beastes (1607): "OF THE VNICORNE", '
                                 "page 711. He has more on that beast: ask again (2 passages).")
    assert embed.url == ("https://archive.org/details/bim_early-english-books-1475-1640_the-historie-of-foure-fo_"
                         "topsell-edward_1607/page/n1/mode/2up?q=question")


def test_other_names_random_and_nothing():
    assert bestiary.bestiary_embed("monoceros").title == "🐉 Unicorn"
    assert bestiary.bestiary_embed("sea unicorn").title == "🐉 Sea-unicorn"
    assert bestiary.bestiary_embed(None).title == "🐉 Unicorn"
    assert "Nothing on that one in this bestiary" in bestiary.bestiary_embed("zzqx").description


def test_command_and_autocomplete():  # Autocompleted on its shelf
    ctx = Ctx(SCOTT)
    run(bestiary.bestiary.callback(ctx, beast="sea-unicorn"))
    assert ctx.last.embed.title == "🐉 Sea-unicorn"
    assert [c.value for c in lore.suggestions("nature", "bestiary", "mono", [bestiary.OLD_BOOK])] == ["Monoceros"]
    assert bestiary.bestiary.aliases == ["topsell"]
