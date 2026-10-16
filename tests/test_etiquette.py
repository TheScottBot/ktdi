"""/etiquette: 1860s etiquette for any situation (ktdi.features.etiquette, ktdi.lib.etiquette)."""

import json
import types

import pytest

from ktdi.features import etiquette
from ktdi.lib import fuzzy
from ktdi.lib import etiquette as situations
from tests.fakes import Ctx, User, run

SCOTT, DAVE = User(1, "scott"), User(2, "dave")
SOUP = {"text": "Never ask for a second helping of soup.", "topics": ["dinner"], "for": None, "book": "hartley"}
LETTER = {"text": "Never write a letter in pencil.", "topics": ["letters"], "for": "gentlemen", "book": "routledge"}
BOW = {"text": "A bow implies acquaintance.", "topics": ["introductions", "street"], "for": "ladies",
       "book": "routledge"}
HIS_HAT = {"text": "He should never wear his hat indoors.", "topics": ["dress"], "for": None, "book": "hartley"}
HER_GLOVES = {"text": "She should keep her gloves on at a ball.", "topics": ["dress", "dancing"], "for": None,
              "book": "routledge"}
MISS_SMITH = {"text": "Address the eldest daughter as Miss Smith.", "topics": ["letters"], "for": None,
              "book": "hartley"}
BOTH = {"text": "A gentleman should offer a lady his arm.", "topics": ["street"], "for": None, "book": "hartley"}
TOPICS = set(situations.SITUATIONS)


@pytest.fixture(autouse=True)
def rules(monkeypatch):
    monkeypatch.setattr(etiquette, "RULES", [SOUP, LETTER, BOW, HIS_HAT, HER_GLOVES, BOTH, MISS_SMITH])


# --- Situations ---
@pytest.mark.parametrize("typed, topic", [
    ("texting", "letters"), ("left on read", "letters"), ("d&d", "games"), ("Dungeons and Dragons", "games"),
    ("vaping", "smoking"), ("meeting her parents", "introductions"), ("splitting the bill", "money"),
    ("movie night", "theatre"), ("talking during a film", "theatre"), ("uber", "travel"),
    ("eating with my mouth open", "dinner"), ("burping", "dinner"), ("sleepover", "guest"), ("the pub", "drinking"),
    ("first date", "conversation"), ("queueing", "street"), ("being late", "general"),
])
def test_situations_find_their_topic(typed, topic):
    assert situations.find_topic(typed)[0] == topic


@pytest.mark.parametrize("typed", ["dave", "xyzzy", "", "   "])
def test_nothing_fits(typed):
    assert situations.find_topic(typed) is None


def test_no_name_is_filed_twice():
    owners = {}
    for topic, name, _ in situations.INDEX:
        owners.setdefault(" ".join(fuzzy.words(name)), set()).add(topic)
    assert {name: found for name, found in owners.items() if len(found) > 1} == {}


def test_suggestions():
    assert "texting" in situations.suggestions("tex")
    assert len(situations.suggestions("")) == 25


# --- Advice, by who it's for ---
def test_who_each_rule_is_for():
    assert etiquette.audience(SOUP) == "anyone"
    assert etiquette.audience(LETTER) == "gentlemen" and etiquette.audience(BOW) == "ladies"  # Tagged
    assert etiquette.audience(HER_GLOVES) == "ladies"  # Untagged Routledge: "she" decides it
    # Hartley wrote to gentlemen, so his rules that mention gentlemen or ladies are for gentlemen
    assert etiquette.audience(HIS_HAT) == etiquette.audience(BOTH) == etiquette.audience(MISS_SMITH) == "gentlemen"
    assert etiquette.pool("anyone") == [SOUP]  # gentlethem never gets a gendered rule


def test_gentleman_gentlewoman_gentlethem(monkeypatch):
    monkeypatch.setattr(etiquette.random, "choice", lambda options: options[0])
    gentleman = etiquette.advice_embed("texting", "gentleman")
    assert gentleman.title == "🎩 Gentleman's etiquette: texting"
    assert gentleman.description == "> Never write a letter in pencil.\n-# Filed under: letters"
    assert gentleman.footer.text == "Routledge's Manual of Etiquette (c. 1875)"
    assert gentleman.url == ("https://www.gutenberg.org/cache/epub/12426/pg12426-images.html"
                             "#:~:text=Never%20write%20a%20letter%20in%20pencil.")  # Open at the rule
    gentlewoman = etiquette.advice_embed("ball", "gentlewoman")
    assert gentlewoman.title == "👒 Gentlewoman's etiquette: ball"
    assert gentlewoman.description.startswith("> She should keep her gloves on at a ball.")
    gentlethem = etiquette.advice_embed("soup", "gentlethem")
    assert gentlethem.title == "🧐 Gentlethem's etiquette: soup"
    assert gentlethem.description.startswith("> Never ask for a second helping of soup.")
    assert etiquette.advice_embed(None, "gentleman").title == "🎩 Gentleman's etiquette"


def test_nothing_fitting_gets_a_shrug_from_the_right_pool():
    embed = etiquette.advice_embed("xyzzy", "gentlethem")
    first, rest = embed.description.split("\n", 1)
    assert any(line.format(situation="xyzzy") == first for line in etiquette.SILENT)
    assert rest == "> Never ask for a second helping of soup."  # The only gentlethem rule
    texting = etiquette.advice_embed("texting", "gentlethem")  # Only the gentlemen have a rule for letters
    assert any(line.format(situation="texting") in texting.description for line in etiquette.SILENT)
    assert "pencil" not in texting.description


def test_commands_and_remind(monkeypatch):
    ctx = Ctx(SCOTT)
    run(etiquette.etiquette_gentlethem.callback(ctx, situation="soup"))
    assert ctx.last.embed.description.startswith("> Never ask for a second helping of soup.")
    run(etiquette.etiquette_gentleman.callback(ctx, situation="dress"))
    assert "hat indoors" in ctx.last.embed.description
    run(etiquette.etiquette_gentlewoman.callback(ctx))
    assert ctx.last.embed.title == "👒 Gentlewoman's etiquette"
    run(etiquette.etiquette_group.callback(ctx, situation="soup"))  # Typed !etiquette soup: gentlethem's
    assert ctx.last.embed.title.startswith("🧐")
    monkeypatch.setattr(etiquette.random, "choice", lambda options: options[0])
    run(etiquette.etiquette_remind.callback(ctx, DAVE))
    assert ctx.last.content == ("🎩 <@1> reminds <@2> of the rules:\n> Never ask for a second helping of soup.\n"
                                "-# Hartley, The Gentlemen's Book of Etiquette (1860)")
    assert [u.id for u in ctx.last.allowed_mentions.users] == [DAVE.id]


def test_autocomplete():
    choices = run(etiquette.situation_autocomplete(types.SimpleNamespace(), "d&"))
    assert "d&d" in [c.value for c in choices]


# --- The real rules ---
def test_the_real_rules_are_well_formed():
    rules = json.loads(etiquette.DATA.read_text(encoding="utf-8"))
    assert len(rules) >= 300
    for rule in rules:
        assert rule["text"].strip() and len(rule["text"]) <= 600, rule
        assert rule["topics"] and set(rule["topics"]) <= TOPICS, rule
        assert rule["book"] in etiquette.BOOKS and rule["for"] in (None, "ladies", "gentlemen"), rule
    assert {topic for rule in rules for topic in rule["topics"]} >= {"dinner", "conversation", "letters", "dress"}
    by_audience = {who: sum(etiquette.audience(r) == who for r in rules) for who in ("gentlemen", "ladies", "anyone")}
    assert all(count >= 40 for count in by_audience.values()), by_audience
