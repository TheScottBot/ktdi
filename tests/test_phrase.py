"""/phrase: where idioms come from, per Brewer's Dictionary of Phrase and Fable (ktdi.features.phrase)."""

import json
import types

import pytest

from ktdi import oldbooks
from ktdi.features import phrase
from tests.fakes import Ctx, User, run

SCOTT = User(1, "scott")
CATS = {"phrase": "To rain cats and dogs", "page": 1048,
        "text": "In northern mythology the cat is supposed to have great influence on the weather."}
HATTER = {"phrase": "Mad as a hatter", "page": 790,
          "text": "Hatter is a corruption of atter (an adder).\n\n“Mad as a March hare” is the same idea."}
BAG = {"phrase": "To let the cat out of the bag", "page": None,
       "text": "To disclose a secret. It was formerly a trick to substitute a cat for a sucking-pig, and bring it in a "
               "bag to market."}


@pytest.fixture(autouse=True)
def phrases(monkeypatch):
    monkeypatch.setattr(phrase, "DICTIONARY", oldbooks.Dictionary(
        [CATS, HATTER, BAG], names=lambda e: [e["phrase"]], text=lambda e: e["text"], close_first=True))
    monkeypatch.setattr(phrase.random, "choice", lambda options: options[0])


def test_an_idiom_however_its_worded():
    for typed in ["to rain cats and dogs", "raining cats and dogs", "it's raining cats and dogs", "mad as a hater"]:
        assert phrase.explain(typed).title in ("🗣️ To rain cats and dogs", "🗣️ Mad as a hatter"), typed
    embed = phrase.explain("raining cats and dogs")
    assert embed.title == "🗣️ To rain cats and dogs"  # The nearest idiom, not a list of everything mentioning cats
    assert embed.description == ("In northern mythology the cat is supposed to have great influence on the weather."
                                 "\n\n-# Brewer was certain.")
    assert embed.footer.text == phrase.SOURCE
    # The scan at its page, with its longest word (the first of the longest) highlighted
    assert embed.url == "https://archive.org/details/dictionaryofphra0000ecob/page/n1048/mode/2up?q=rain"


def test_paragraphs_and_a_missing_page():
    assert "atter (an adder).\n\n“Mad as a March hare”" in phrase.explain("mad as a hatter").description
    assert phrase.explain("let the cat out of the bag").url == \
        "https://archive.org/details/dictionaryofphra0000ecob?q=let"


def test_idioms_that_mention_a_word():
    embed = phrase.explain("secret")
    assert embed.title == "🗣️ Idioms that mention “secret”"
    assert embed.description.startswith(f"**[To let the cat out of the bag]({phrase.url(BAG)})**: To disclose")


def test_nothing_found_and_random():
    assert "Nothing from Brewer on that here" in phrase.explain("zzqx").description
    assert phrase.explain(None).title == "🗣️ To rain cats and dogs"
    assert phrase.explain("the").title == "🗣️ To rain cats and dogs"  # Only filler: random


def test_command_and_autocomplete():
    ctx = Ctx(SCOTT)
    run(phrase.phrase.callback(ctx, idiom="mad as a hatter"))
    assert ctx.last.embed.title == "🗣️ Mad as a hatter"
    choices = run(phrase.idiom_autocomplete(types.SimpleNamespace(), "cat"))
    assert [c.value for c in choices] == ["To let the cat out of the bag", "To rain cats and dogs"]
    assert phrase.phrase.aliases == ["idiom", "brewer"]


def test_the_real_idioms_are_well_formed():
    idioms = json.loads(phrase.DATA.read_text(encoding="utf-8"))
    assert len(idioms) >= 1000
    for entry in idioms:
        assert entry["phrase"].strip() and entry["text"].strip(), entry
        assert entry["page"] is None or 0 <= entry["page"] < 1458, entry  # Images in the scan
        assert "(See " not in entry["text"], entry["phrase"]  # Cross-references lead nowhere here
    assert len({e["phrase"].casefold() for e in idioms}) == len(idioms)  # No idiom twice
    by_phrase = {e["phrase"]: e for e in idioms}
    assert "Mad as a hatter" in by_phrase and "To let the cat out of the bag" in by_phrase
