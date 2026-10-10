"""/cure: Culpeper's remedies (ktdi.features.cure), the ailment lookup (ktdi.lib.cure, ktdi.lib.ailments) and the
build from the herbal (ktdi.tools.cure_build)."""

import types

import pytest

from ktdi.features import cure
from ktdi.lib import cure as lookup
from ktdi.lib.ailments import AILMENTS
from ktdi.tools import cure_build as build
from tests.fakes import Ctx, User, run


@pytest.mark.parametrize("typed, ailment", [
    ("tickly throat", "sore throat"), ("my throat is tickly", "sore throat"), ("Sore Throat", "sore throat"),
    ("the flu", "flu"), ("man flu", "flu"), ("diarhea", "diarrhoea"), ("the runs", "diarrhoea"),
    ("missing an arm", "missing limb"), ("I've lost an arm", "missing limb"), ("beheaded", "missing limb"),
    ("hung over", "hangover"), ("got dumped", "heartbreak"), ("can't sleep", "insomnia"), ("cant sleep", "insomnia"),
    ("my head hurts", "headache"), ("migrane", "headache"), ("existential dread", "melancholy"),
    ("being dead", "death"), ("werewolf", "cursed"), ("stubbed toe", "bruises"), ("athletes foot", "itch"),
    ("pain in the arse", "piles"), ("covid", "plague"), ("a nasty case of the plague", "plague"),
    ("erectile dysfunction", "low libido"), ("mondays", "tiredness"), ("ugly", "complexion"),
    ("my back hurts", "back pain"), ("broken leg", "broken bones"), ("hay fever", "common cold"),
])
def test_finds_what_people_mean(typed, ailment):
    assert lookup.find(typed).ailment.name == ailment


@pytest.mark.parametrize("typed", ["dave", "", "   ", "the", "xyzzy plugh"])
def test_nothing_for_nonsense(typed):
    assert lookup.find(typed) is None


def test_exact_and_fuzzy_matches_are_told_apart():
    assert lookup.find("tickly throat").exact and not lookup.find("my throat is tickly").exact


def test_no_name_belongs_to_two_ailments():
    owners = {}
    for a in AILMENTS:
        for name in a.names:
            owners.setdefault(" ".join(lookup.words(name)), set()).add(a.name)
    assert {name: found for name, found in owners.items() if len(found) > 1} == {}


def test_every_ailment_has_remedies_and_none_are_left_out_ones():
    remedies = cure.data["remedies"]
    assert set(remedies) == {a.name for a in AILMENTS}
    assert all(remedies[a.name] for a in AILMENTS), [a.name for a in AILMENTS if not remedies[a.name]]
    for found in remedies.values():
        for remedy in found:
            assert not build.LEFT_OUT.search(remedy["text"]) and "_" not in remedy["text"]
            assert len(remedy["text"]) <= build.MAX_LENGTH + 2
    assert cure.data["allheal"]


def test_culpeper_terms_match_whole_words_unless_stems():
    insomnia = next(a for a in AILMENTS if a.name == "insomnia")
    assert insomnia.pattern.search("it procures sleep") and not insomnia.pattern.search("it restrains the flux")
    cold = next(a for a in AILMENTS if a.name == "common cold")
    assert cold.pattern.search("it stops sneezing")  # "sneez*" is a stem


def test_suggestions():
    assert set(lookup.suggestions("tick")) == {"tickly throat", "tickly cough"}
    assert "sore throat" in lookup.suggestions("throat")
    assert len(lookup.suggestions("")) == 25


BOOK = """
    WATER AGRIMONY.

_Descript._] The root continues a long time.

_Government and virtues._] It is a plant of Jupiter. It helps the
_yellow-jaundice_. It kills worms, and helps the cough: It consolidates
green wounds. It is good to bring away the dead child.

    ALL-HEAL.

_Government and virtues._] It is called All-heal, because it heals all diseases of the body.
"""


def test_build_reads_each_herbs_virtues():
    assert build.herbs(BOOK) == [
        ("Water Agrimony", "It is a plant of Jupiter. It helps the yellow-jaundice. It kills worms, and helps the "
                           "cough: It consolidates green wounds. It is good to bring away the dead child."),
        ("All-Heal", "It is called All-heal, because it heals all diseases of the body.")]
    data = build.build(BOOK)
    assert [r["text"] for r in data["remedies"]["worms"]] == ["It kills worms, and helps the cough:"]
    limb = data["remedies"]["missing limb"][0]
    assert limb["text"][slice(*limb["match"])] == "consolidates"  # bolded to the end of the word
    assert not any("dead child" in r["text"] for found in data["remedies"].values() for r in found)
    assert data["allheal"][0]["herb"] == "All-Heal"


def test_long_sentences_are_cut_around_the_match():
    sentence = "word " * 100 + "it helps the gout " + "word " * 100
    text, start = build.shorten(sentence, sentence.index("gout"))
    assert len(text) <= build.MAX_LENGTH + 2 and text[start:start + 4] == "gout" and text[0] == text[-1] == "…"


def test_cure_embed(monkeypatch):
    monkeypatch.setattr(cure.random, "choice", lambda options: options[0])
    monkeypatch.setitem(cure.data["remedies"], "sore throat",
                        [{"herb": "Sage", "text": "It helps the quinsy *wonderfully*.", "match": [13, 19]}])
    embed = cure.cure_embed("my throat is tickly")
    assert embed.title == "🌿 A cure for my throat is tickly"
    assert embed.description == "**Sage**: It helps the **quinsy** \\*wonderfully\\*.\n-# Filed under: sore throat"
    assert embed.footer.text == "Culpeper's Complete Herbal (1653)"
    assert "Filed under" not in cure.cure_embed("sore throat").description  # asked for it by name


def test_nothing_matching_gets_all_heal(monkeypatch):
    monkeypatch.setattr(cure.random, "choice", lambda options: options[0])
    monkeypatch.setitem(cure.data, "allheal", [{"herb": "All-Heal", "text": "It heals all.", "match": [0, 0]}])
    embed = cure.cure_embed("dave")
    assert embed.description == "Culpeper has never heard of *dave*, but swears by **All-Heal**:\n> It heals all."


def test_cure_command_and_autocomplete():
    ctx = Ctx(User(1, "scott"))
    run(cure.cure.callback(ctx, ailment="hangover"))
    assert ctx.last.embed.title == "🌿 A cure for hangover"
    choices = run(cure.ailment_autocomplete(types.SimpleNamespace(), "hang"))
    assert "hangover" in [c.value for c in choices]
