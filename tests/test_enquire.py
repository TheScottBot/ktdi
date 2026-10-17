"""/enquire: Enquire Within Upon Everything (ktdi.features.enquire, ktdi.tools.enquire_build)."""

import json

import pytest

from ktdi.features import enquire, lore
from ktdi.tools import enquire_build as build
from tests.fakes import Ctx, User, run

SCOTT = User(1, "scott")

BOOK = """Preface.

CHOICE OF FOOD, MARKETING, ETC.                                  1

INDOOR GAMES AND AMUSEMENTS                                     45

POISONING, TREATMENT IN CASES OF                                50

FUEL, LIGHTING, ETC., ECONOMY AND MANAGEMENT OF                 60


                                  ENQUIRE WITHIN


1. Choice of Articles of Food.

  Nothing is more important in the affairs of housekeeping than the
  choice of wholesome food.


2. Mackerel

  must be perfectly fresh, or it is a very indifferent fish.


31. In Season in January.

  i. Fish.

  Barbel, brill, carp, cod.


45. Whist.

  Great silence and attention should be observed by the players.

      Ace   King
      Queen   Knave


50. Arsenic.

  Give an emetic at once.


60. Lighting Candles.

  In lighting candles always hold the match to the side of the wick.


61. Candles

  improve by keeping a few months.


INDEX OF ENQUIRIES

*** END OF THE PROJECT GUTENBERG EBOOK
"""


@pytest.fixture(autouse=True)
def hints(monkeypatch):
    monkeypatch.setattr(enquire, "DICTIONARY", enquire.dictionary(build.entries(BOOK)))
    monkeypatch.setattr(enquire.oldbooks.random, "choice", lambda options: options[0])


# --- Reading the book ---
def test_hints_are_read_from_the_book():
    found = {e["number"]: e for e in build.entries(BOOK)}
    assert sorted(found) == [1, 2, 31, 45, 60, 61]  # Poisoning is left out whole
    assert found[60] == {"number": 60, "title": "Lighting Candles",
                         "text": "In lighting candles always hold the match to the side of the wick."}
    assert found[2]["text"] == "Mackerel must be perfectly fresh, or it is a very indifferent fish."  # Runs on
    assert found[31]["text"] == "i. Fish.\n\nBarbel, brill, carp, cod."  # A list, not a run-on title
    assert found[45]["text"].endswith("players.\n\nAce   King\nQueen   Knave")  # Laid out: its lines kept
    assert build.key(found[60]) == "60. Lighting Candles"


def test_the_real_data_is_exactly_whats_on_the_allowlist():
    curation = json.loads(build.CURATION.read_text(encoding="utf-8"))
    assert set(curation) == {"_about", "keep"}
    real = json.loads(enquire.DATA.read_text(encoding="utf-8"))["entries"]
    assert len(real) >= 1500
    assert [build.key(e) for e in real] == curation["keep"]
    for hint in real:
        assert hint["title"].strip() and hint["text"].strip(), hint["number"]
    # Nearly every hint links to its place; a few start in quotes and apostrophes, and open the book instead.
    assert sum("#:~:text=" in enquire.url(hint) for hint in real) >= len(real) * 0.98


# --- Asking ---
def test_a_hint_and_how_many_more():
    assert enquire.enquire_embed("candles").title == "🔎 Candles"  # Its title, exactly
    embed = enquire.enquire_embed("candle")  # Not a title: the hints about it
    assert embed.title == "🔎 Lighting Candles"
    assert embed.description == "In lighting candles always hold the match to the side of the wick."
    assert embed.footer.text == f"{enquire.SOURCE}. There's more on that: ask again (2 hints)."
    assert enquire.enquire_embed("whist").footer.text == enquire.SOURCE  # Only the one


def test_laid_out_text_is_a_block():
    assert enquire.enquire_embed("whist").description.endswith("```\nAce   King\nQueen   Knave\n```")


def test_links_go_to_the_hints_heading():
    hint = {"number": 60, "title": "Lighting Candles", "text": "In lighting candles always hold the match."}
    assert enquire.url(hint).endswith("#:~:text=60.%20Lighting%20Candles")
    # An accent stops the heading being findable by its number: the hint's first words instead
    accented = {"number": 118, "title": "Ecarté", "text": "This game is played by two persons with a pack of cards."}
    assert enquire.url(accented).endswith("#:~:text=This%20game%20is%20played%20by%20two%20persons%20with%20a%20pack")


def test_random_and_nothing():
    assert enquire.enquire_embed(None).title == "🔎 Choice of Articles of Food"
    assert "Nothing on that here, despite the name" in enquire.enquire_embed("zzqx").description


def test_command_and_autocomplete():  # Autocompleted on its shelf
    ctx = Ctx(SCOTT)
    run(enquire.enquire.callback(ctx, anything="mackerel"))
    assert ctx.last.embed.title == "🔎 Mackerel"
    choices = lore.suggestions("household", "enquire", "candle", [enquire.OLD_BOOK])
    assert [c.value for c in choices] == ["Candles", "Lighting Candles"]
    assert enquire.enquire.aliases == ["enquirewithin", "ewue"]
