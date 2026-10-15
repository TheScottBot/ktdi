"""/secrets: The Boke of Secretes of Albertus Magnus (ktdi.features.secrets, ktdi.tools.secrets_build; reading the book
is tests/test_tcp.py)."""

import json
import types

import pytest

from ktdi.features import secrets
from ktdi.tools import secrets_build as build, tcp
from tests.fakes import Ctx, User, run

SCOTT = User(1, "scott")

# Sections are numbered as in the real book, so their parts (herbs, stones, marvels) come out right
FILLER = "".join(f"<div><head>Section {n}</head><p>Nothing.</p></div>" for n in range(4, 52))
BOOK = f"""<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
<div><head>❧ The fyrste boke of the vertues of certayne Herbes.</head>
<p>¶ The firste herbe is called with English men, Marygolde, &amp; a wolues tothe be added therto, no man shalbe able
to haue a word to speake against the bearer therof.</p></div>
<div><head>Herbs of the planets</head><p>Nothing.</p></div>
<div><head>Stones</head><p>Nothing.</p></div>
<div><head>☞ If thou wilt knowe whyther thy wyfe is chaste, or no.</head>
<p>Take the stone, which is called Magnes in English, the lode stone. Laye thys stone vnder the head of a wyfe.</p>
</div>
{FILLER}
<div><head>¶ If thou wilt louse bondes.</head>
<p>Go into the woode, and loke where the Pye hath her nest.</p>
<p>¶ A meruaylous operation of a lampe, whiche yf anye man shall holde, he ceaseth not to farte.</p>
<p>¶ Take the bloude of a snayl, drye it vp in a linen cloth, &amp; make of it a weke.</p></div>
</body></text></TEI>"""

CURATION = {"keep": {
    "secrets:0": {"head": "The fyrste boke of the vertues of certayne Herbes", "name": "Herb",
                  "paragraphs": [{"number": 0, "name": "Marigold", "also": ["Peace"]}]},
    "secrets:3": {"head": "If thou wilt knowe whyther thy wyfe is chaste, or no", "name": "Lodestone",
                  "also": ["Magnet"], "paragraphs": [0]},
    "secrets:52": {"head": "If thou wilt louse bondes", "name": "Magpie",
                   "paragraphs": [0, {"number": 2, "name": "Lamp", "also": ["Fart"], "title": 1}]},
}}


@pytest.fixture(autouse=True)
def passages(monkeypatch):
    found = tcp.kept({"secrets": BOOK}, CURATION)
    assert found["missing"] == []
    monkeypatch.setattr(secrets, "DICTIONARY", secrets.dictionary(found["passages"]))
    monkeypatch.setattr(secrets.oldbooks.random, "choice", lambda options: options[0])


def test_the_real_secrets_are_on_the_allowlist():
    curation = json.loads(build.CURATION.read_text(encoding="utf-8"))
    real = json.loads(secrets.DATA.read_text(encoding="utf-8"))["passages"]
    numbers = [(key, n["number"] if isinstance(n, dict) else n) for key, kept in curation["keep"].items()
               for n in kept["paragraphs"]]
    assert [p["key"] for p in real] == [f"{key}:{n}" for key, n in numbers]
    assert len(real) >= 80 and all(p["text"] and secrets.title(p) for p in real)
    shown = " ".join(p["text"] for p in real)
    for harmful in ("Arsenicum", "quycke syluer", "quicke siluer", "Auri pigmentum", "brymstone"):
        assert harmful not in shown  # Nothing anyone could make and be hurt by


# --- The command ---
def test_a_stone_is_titled_by_what_its_for():
    embed = secrets.secrets_embed("lodestone")
    assert embed.title == "🗝️ If thou wilt knowe whyther thy wyfe is chaste, or no"
    assert embed.description == ("Take the stone, which is called Magnes in English, the lode stone. Laye thys stone "
                                 "vnder the head of a wyfe.")
    assert embed.footer.text == f"{secrets.SOURCE}, of stones."
    assert embed.url.startswith(f"https://archive.org/details/{secrets.SCAN}/page/n")


def test_a_herb_is_titled_by_its_name_and_a_marvel_by_its_own_title():
    assert secrets.secrets_embed("marigold").title == "🗝️ Marigold"
    assert secrets.secrets_embed("marigold").footer.text == f"{secrets.SOURCE}, of herbs."
    embed = secrets.secrets_embed("fart")  # By a tag
    assert embed.title == ("🗝️ A meruaylous operation of a lampe, whiche yf anye man shall holde, he ceaseth not to "
                           "farte")
    assert embed.description.startswith("Take the bloude of a snayl")
    assert embed.footer.text == f"{secrets.SOURCE}, the Meruayles of the World."


def test_found_in_modern_spelling():
    assert secrets.secrets_embed("wife").title.startswith("🗝️ If thou wilt knowe whyther thy wyfe")  # "wyfe"
    assert secrets.secrets_embed("magnet").title.startswith("🗝️ If thou wilt knowe")
    assert secrets.secrets_embed("peace").title == "🗝️ Marigold"


def test_random_and_nothing():
    assert secrets.secrets_embed(None).title == "🗝️ Marigold"
    assert "No secret about that here" in secrets.secrets_embed("zzqx").description


def test_command_and_autocomplete():
    ctx = Ctx(SCOTT)
    run(secrets.secrets.callback(ctx, what="magpie"))
    assert ctx.last.embed.title == "🗝️ If thou wilt louse bondes"
    assert [c.value for c in run(secrets.what_autocomplete(types.SimpleNamespace(), "lode"))] == ["Lodestone"]
    assert secrets.secrets.aliases == ["albertus"]
