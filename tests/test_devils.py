"""/devils: Ambrose Bierce's The Devil's Dictionary (ktdi.features.devils, ktdi.tools.devils_build)."""

import hashlib
import json
import types
from pathlib import Path

import pytest

from ktdi.features import devils
from ktdi.tools import devils_build as build, gutenberg
from tests.fakes import Ctx, User, run

SCOTT = User(1, "scott")
# SHA-256 fingerprints of the headwords of entries that were taken out, so this can check they stay out without the
# repo spelling any of them out.
LEFT_OUT = set(json.loads((Path(__file__).parent / "devils_left_out.sha256.json").read_text(encoding="utf-8")))

BOOK = """Title page.

THE DEVIL'S DICTIONARY

A

ABRACADABRA.

  By _Abracadabra_ we signify
  An infinite number of things.

Jamrach Holobom

BABE or BABY, n.  A misshapen creature of no particular age, sex, or
condition.

  Ere babes were invented
  The girls were contented.

G.J.

BORE, n.  A person who talks when you wish him to listen.

I

I is the first letter of the alphabet--the first word of the language.

IMPOSTOR n.  A rival aspirant to public honors.

R

R.I.P.  A careless abbreviation of _requiescat in pace_.

REASON, v.i.  To weigh probabilities in the scales of desire.

REASON, n.  Propensitate of prejudice.

T

TZETZE (or TSETSE) FLY, n.  An African insect whose bite is a remedy for insomnia.

*** END OF THE PROJECT GUTENBERG EBOOK
"""


@pytest.fixture(autouse=True)
def entries(monkeypatch):
    test_entries = build.entries(BOOK)
    monkeypatch.setattr(devils, "DICTIONARY", devils.dictionary(test_entries))
    monkeypatch.setattr(devils.random, "choice", lambda options: options[0])
    monkeypatch.setattr(devils.random, "sample", lambda options, n: list(options)[:n])


# --- Reading the book ---
def test_the_book_is_split_into_entries():
    found = build.entries(BOOK)
    # Verse signatures ("G.J.") and the section letters aren't entries; the letters' own entries are.
    assert [e["word"] for e in found] == ["ABRACADABRA", "BABE or BABY", "BORE", "I", "IMPOSTOR", "R.I.P.", "REASON",
                                          "REASON", "TZETZE (or TSETSE) FLY"]
    by_word = {e["word"]: e for e in found}
    assert by_word["BORE"] == {"word": "BORE", "pos": "n.", "head": "BORE, n.",
                               "text": "A person who talks when you wish him to listen."}
    assert by_word["BABE or BABY"]["text"] == ("A misshapen creature of no particular age, sex, or condition.\n\n"
                                               "Ere babes were invented\nThe girls were contented.\n\nG.J.")
    assert by_word["ABRACADABRA"]["head"] == "ABRACADABRA." and by_word["ABRACADABRA"]["pos"] == ""
    assert by_word["IMPOSTOR"]["head"] == "IMPOSTOR n."  # As the book has it (no comma), for the link
    assert by_word["I"]["head"] == "" and by_word["I"]["text"].startswith("I is the first letter")
    assert by_word["R.I.P."]["text"] == "A careless abbreviation of _requiescat in pace_."


def test_build_keeps_only_the_allowlist():
    kept = gutenberg.kept(build.entries(BOOK), ["BORE", "REASON"])
    assert [e["word"] for e in kept] == ["BORE", "REASON", "REASON"]


def test_what_was_taken_out_stays_out():
    real = json.loads(devils.DATA.read_text(encoding="utf-8"))["entries"]
    assert len(LEFT_OUT) >= 50
    for entry in real:
        assert hashlib.sha256(entry["word"].encode("utf-8")).hexdigest() not in LEFT_OUT, entry["word"]


def test_the_real_dictionary_is_exactly_whats_on_the_allowlist():
    curation = json.loads(build.CURATION.read_text(encoding="utf-8"))
    assert set(curation) == {"_about", "keep"}  # Nothing records what was taken out.
    real = json.loads(devils.DATA.read_text(encoding="utf-8"))["entries"]
    assert len(real) >= 900
    assert {e["word"] for e in real} == set(curation["keep"])
    for entry in real:
        assert entry["word"].strip() and entry["text"].strip(), entry
        assert devils.url(entry).count("#:~:text=") == 1, entry["word"]  # Every entry links to its place


# --- Looking things up ---
def test_a_word_by_name_with_typos():
    for typed in ["bore", "BORE", "a bore", "boor"]:
        assert devils.devils_embed(typed).title == "😈 BORE", typed
    embed = devils.devils_embed("bore")
    assert embed.description == "*n.* A person who talks when you wish him to listen."
    assert embed.footer.text == devils.SOURCE
    assert embed.url == ("https://www.gutenberg.org/cache/epub/972/pg972-images.html#:~:text="
                         "BORE%2C%20n.%20A%20person%20who%20talks%20when%20you%20wish%20him")


def test_every_name_an_entry_goes_by():
    assert devils.names("BABE or BABY") == ["BABE", "BABY"]
    assert devils.names("TZETZE (or TSETSE) FLY") == ["TZETZE FLY", "TSETSE FLY"]
    assert devils.devils_embed("baby").title == "😈 BABE or BABY"
    assert devils.devils_embed("tsetse fly").title == "😈 TZETZE (or TSETSE) FLY"


def test_headwords_the_loose_matching_ignores():
    assert devils.devils_embed("I").title == "😈 I"  # "I" is a word fuzzy matching skips
    assert devils.devils_embed("i").description.startswith("I is the first letter of the alphabet—the first word")


def test_verse_is_quoted_and_signed():
    assert devils.devils_embed("babe").description == (
        "*n.* A misshapen creature of no particular age, sex, or condition.\n\n"
        "> Ere babes were invented\n> The girls were contented.\n-# G.J.")
    assert devils.devils_embed("abracadabra").description == (
        "> By *Abracadabra* we signify\n> An infinite number of things.\n-# Jamrach Holobom")


def test_a_word_with_two_entries_shows_both():
    assert devils.devils_embed("reason").description == (
        "*v.i.* To weigh probabilities in the scales of desire.\n\n*n.* Propensitate of prejudice.")


def test_long_entries_are_cut_short():
    entry = {"word": "LONG", "pos": "n.", "head": "LONG, n.", "text": "Word " * 100 + "\n\nAnother paragraph."}
    text = devils.entry_text(entry, limit=100)
    assert len(text) < 140 and text.endswith("…\n\n*…the rest is in the book.*")
    assert devils.entry_text(entry, limit=510).endswith("Word\n\n*…the rest is in the book.*")  # The second won't fit
    assert devils.entry_text(entry, limit=1000).endswith("Word\n\nAnother paragraph.")  # Room for it all


def test_a_plain_word_finds_the_entries_that_use_it():
    embed = devils.devils_embed("prejudice")
    assert embed.title == "😈 Bierce on “prejudice”"
    reason = devils.DICTIONARY.entries[-2]
    assert reason["text"] == "Propensitate of prejudice."
    assert embed.description == f"**[REASON]({devils.url(reason)})**: Propensitate of prejudice."
    assert embed.url is None  # Each entry links to its own place, not the list to the book's front


def test_nothing_found():
    assert "Bierce never got round to that one" in devils.devils_embed("zzqx").description


def test_random():
    assert devils.devils_embed(None).title == "😈 ABRACADABRA"
    assert devils.devils_embed("   ").title == "😈 ABRACADABRA"


def test_command_and_autocomplete():
    ctx = Ctx(SCOTT)
    run(devils.devils.callback(ctx))
    assert ctx.last.embed.title == "😈 ABRACADABRA"
    run(devils.devils.callback(ctx, word="bore"))
    assert ctx.last.embed.title == "😈 BORE"
    choices = run(devils.word_autocomplete(types.SimpleNamespace(), "re"))
    assert [c.value for c in choices] == ["REASON", "BORE"]  # Starting with it first, then containing it
    assert devils.devils.aliases == ["devil", "devilsdictionary"]
