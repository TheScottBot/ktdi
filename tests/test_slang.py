"""/vulgartongue: 1811 slang from Grose's Dictionary of the Vulgar Tongue (ktdi.features.slang, ktdi.tools.slang_build)."""

import hashlib
import json
import types
from pathlib import Path

from ktdi import oldbooks
from ktdi.features import slang
from ktdi.tools import slang_build as build
from tests.fakes import Ctx, User, run

SCOTT, DAVE = User(1, "scott"), User(2, "dave")
# SHA-256 fingerprints of the headwords of entries that were taken out (slurs and the rest), so this can check they
# stay out without the repo spelling any of them out.
LEFT_OUT = set(json.loads((Path(__file__).parent / "slang_left_out.sha256.json").read_text(encoding="utf-8")))


# --- What's in the dictionary ---
def test_what_was_taken_out_stays_out():
    assert len(LEFT_OUT) > 1000
    for entry in slang.ENTRIES:
        assert hashlib.sha256(entry["word"].encode("utf-8")).hexdigest() not in LEFT_OUT, entry["word"]


def test_the_dictionary_is_exactly_whats_on_the_allowlist():
    curation = json.loads(build.CURATION.read_text(encoding="utf-8"))
    assert set(curation) == {"_about", "keep", "insults"}  # Nothing records what was taken out.
    for entry in slang.ENTRIES:
        assert build.picked(entry, curation["keep"]), entry["word"]
        assert entry["insult"] == build.picked(entry, curation["insults"]), entry["word"]


def test_there_are_plenty_of_insults_and_they_describe_people():
    assert len(slang.INSULTS) >= 200 and len(slang.ENTRIES) >= 2500
    by_word = {e["word"]: e for e in slang.INSULTS}
    assert by_word["CAPTAIN QUEERNABS"]["text"] == "A shabby ill-dressed fellow."
    assert by_word["JACOB"]["text"].startswith("A soft fellow")  # not the JACOB that's a ladder
    assert not any(e["word"] == "JACOB" and "ladder" in e["text"] for e in slang.INSULTS)


BOOK = """Preface.

DICTIONARY OF THE VULGAR TONGUE.


ADDLE PATE. An inconsiderate foolish fellow.

BUBBLE. A cheated fellow.

JACOB. A soft fellow. A fool.

JACOB. A ladder: perhaps from
  Jacob's dream. CANT.

TO HOP THE TWIG. To run away. CANT.
  Where shall we go?
  Over the hills.

*** END OF THE PROJECT GUTENBERG EBOOK
"""


def test_build_keeps_only_the_allowlist_and_picks_insults():
    found = build.entries(BOOK)
    assert [e["word"] for e in found] == ["ADDLE PATE", "BUBBLE", "JACOB", "JACOB", "TO HOP THE TWIG"]
    assert found[3]["text"] == "A ladder: perhaps from Jacob's dream. CANT."
    assert found[4]["text"] == "To run away. CANT. Where shall we go? Over the hills."  # verse joins its entry
    data = build.build(BOOK, {"keep": ["ADDLE PATE", "JACOB", "TO HOP THE TWIG :: To run"],
                              "insults": ["ADDLE PATE", "JACOB :: A soft fellow"]})
    assert [(e["word"], e["insult"]) for e in data["entries"]] == [
        ("ADDLE PATE", True), ("JACOB", True), ("JACOB", False), ("TO HOP THE TWIG", False)]  # BUBBLE isn't kept


# --- Looking things up ---
def test_display_word():
    assert slang.display_word("CAPTAIN QUEERNABS") == "Captain Queernabs"
    assert slang.display_word("TO HOP THE TWIG") == "To Hop the Twig"
    assert slang.display_word("CAKE, or CAKEY") == "Cake, or Cakey"
    assert slang.display_word("COD'S HEAD") == "Cod's Head"


def test_a_word_by_name_with_typos():
    for typed in ["captain queernabs", "Captain  Queernabs", "captain queernab", "queernabs captain"]:
        embed = slang.slang_embed(typed)
        assert embed.title == "📖 Captain Queernabs" and embed.description == "A shabby ill-dressed fellow."
    assert slang.slang_embed("addlepate").title == "📖 Addle Pate"
    assert slang.slang_embed("cakey").title == "📖 Cake, or Cakey"  # either name
    assert slang.slang_embed("captain queernabs").url == (
        "https://www.gutenberg.org/cache/epub/5402/pg5402-images.html"
        "#:~:text=CAPTAIN%20QUEERNABS.%20A%20shabby%20ill%2Ddressed%20fellow.")  # Open at the entry


def test_a_plain_word_finds_the_slang_for_it():
    embed = slang.slang_embed("coward")
    assert embed.title == "📖 “coward”, in 1811"
    assert "**Chicken-Hearted**: Fearful, cowardly." in embed.description
    assert "**White-Livered**: Cowardly, malicious." in embed.description


def test_a_word_in_the_dictionary_also_lists_other_ways_to_say_it():
    embed = slang.slang_embed("drunk")
    assert embed.title == "📖 Drunk"
    [others] = embed.fields
    assert others.name == "Other ways to say “drunk”" and " · " in others.value


def test_lots_of_matches_are_sampled():
    embed = slang.slang_embed("money")
    assert embed.description.count("\n") == oldbooks.SHOWN - 1
    assert "ask again for others" in embed.footer.text
    assert all(len(line) <= oldbooks.LINE_LENGTH for line in embed.description.split("\n"))


def test_nothing_found():
    embed = slang.slang_embed("zzqx")
    assert "Grose never wrote that down" in embed.description


def test_random_entry_is_never_an_insult(monkeypatch):
    embed = slang.slang_embed(None)
    assert embed.title.startswith("📖 ") and embed.footer.text == slang.SOURCE
    picked_from = []
    monkeypatch.setattr(slang.random, "choice", lambda options: picked_from.append(options) or options[0])
    slang.slang_embed(None)
    slang.slang_embed("   ")
    run(slang.slang_random.callback(Ctx(SCOTT)))
    assert all(options is slang.PHRASES for options in picked_from) and len(picked_from) == 3
    assert slang.PHRASES and not any(e["insult"] for e in slang.PHRASES)
    assert len(slang.PHRASES) + len(slang.INSULTS) == len(slang.ENTRIES)


# --- The command ---
def test_insulting_someone(monkeypatch):
    queernabs = next(e for e in slang.INSULTS if e["word"] == "CAPTAIN QUEERNABS")
    monkeypatch.setattr(slang.random, "choice", lambda options: queernabs)
    ctx = Ctx(SCOTT)
    run(slang.slang_insult.callback(ctx, DAVE))
    assert ctx.last.content == ("🎩 <@1> has insulted <@2>, in the words of 1811:\n# Captain Queernabs!\n"
                                "> A shabby ill-dressed fellow.\n-# Grose's Dictionary of the Vulgar Tongue (1811)")
    assert [u.id for u in ctx.last.allowed_mentions.users] == [DAVE.id]  # only the insulted is pinged


def test_command_looks_up_words():
    ctx = Ctx(SCOTT)
    run(slang.slang.callback(ctx, word="addle pate"))
    assert ctx.last.embed.title == "📖 Addle Pate"
    run(slang.slang.callback(ctx))
    assert ctx.last.embed.title.startswith("📖 ")


def test_autocomplete():
    choices = run(slang.word_autocomplete(types.SimpleNamespace(), "captain q"))
    assert "Captain Queernabs" in [c.value for c in choices]
    assert len(run(slang.word_autocomplete(types.SimpleNamespace(), ""))) == 25
