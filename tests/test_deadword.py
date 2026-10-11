"""/deadword: words English stopped using, from Mackay's Lost Beauties of the English Language (ktdi.features.deadword)."""

import json
import types

import pytest

from ktdi.features import deadword
from ktdi.lib import fuzzy
from tests.fakes import Ctx, User, run

SCOTT = User(1, "scott")
BEVER = {"word": "Bever", "meaning": "a drink between meals.",
         "quote": "Thirty meals a day, and ten bevers, a small trifle to suffice nature.",
         "quote_source": "Marlowe: Dr. Faustus"}
BICKER = {"word": "Bicker", "meaning": "a drinking cup, a beaker.", "quote": None, "quote_source": None}
BELL_PENNY = {"word": "Bell-penny", "meaning": "money laid up by any one to pay the expenses of his own funeral.",
              "quote": "Line one, / line two", "quote_source": None}


@pytest.fixture(autouse=True)
def words(monkeypatch):
    test_words = [BEVER, BICKER, BELL_PENNY]
    monkeypatch.setattr(deadword, "WORDS", test_words)
    monkeypatch.setattr(deadword, "INDEX", fuzzy.index((e, e["word"]) for e in test_words))
    monkeypatch.setattr(deadword, "ALL_WORDS", ["Bell-penny", "Bever", "Bicker"])
    monkeypatch.setattr(deadword.random, "choice", lambda options: options[0])


def test_a_dead_word_by_name_with_typos():
    for typed in ["bever", "Bever", "bevor", "bell penny", "bellpenny"]:
        assert deadword.deadword_embed(typed).title in ("📜 Bever", "📜 Bell-penny"), typed
    embed = deadword.deadword_embed("bever")
    assert embed.description == ("*A drink between meals.*\n\n"
                                 "> Thirty meals a day, and ten bevers, a small trifle to suffice nature.\n"
                                 "-# Marlowe: Dr. Faustus\n\n🪦 Here lies a perfectly good word.")
    assert embed.footer.text == deadword.SOURCE and embed.url == deadword.SOURCE_URL


def test_a_verse_quote_is_quoted_line_by_line():
    assert "> Line one,\n> line two\n\n🪦" in deadword.deadword_embed("bell-penny").description


def test_a_plain_word_finds_the_dead_words_for_it():
    embed = deadword.deadword_embed("drink")
    assert embed.title == "📜 Dead words for “drink”"
    assert "**Bever**: a drink between meals." in embed.description
    assert "**Bicker**: a drinking cup, a beaker." in embed.description
    assert "Bell-penny" not in embed.description


def test_nothing_found():
    assert "Mackay never mourned that one" in deadword.deadword_embed("zzqx").description


def test_random():
    assert deadword.deadword_embed(None).title == "📜 Bever"
    assert deadword.deadword_embed("   ").title == "📜 Bever"


def test_command_and_autocomplete():
    ctx = Ctx(SCOTT)
    run(deadword.deadword.callback(ctx))
    assert ctx.last.embed.title == "📜 Bever"
    run(deadword.deadword.callback(ctx, word="bicker"))
    assert ctx.last.embed.title == "📜 Bicker"
    choices = run(deadword.word_autocomplete(types.SimpleNamespace(), "be"))
    assert [c.value for c in choices] == ["Bell-penny", "Bever"]


def test_the_real_words_are_well_formed():
    words = json.loads(deadword.DATA.read_text(encoding="utf-8"))
    assert len(words) >= 500
    for entry in words:
        assert entry["word"].strip() and entry["meaning"].strip(), entry
        assert len(entry["meaning"]) <= 600, entry
        assert (entry["quote"] is None) or entry["quote"].strip(), entry
    assert len({e["word"].casefold() for e in words}) == len(words)  # No word twice
