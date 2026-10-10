"""/cure and /plant: Culpeper's remedies (ktdi.features.cure), the ailment and plant lookups (ktdi.lib.cure,
ktdi.lib.ailments) and the build from the herbal (ktdi.tools.cure_build)."""

import json
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
    ("my back hurts", "back pain"), ("broken leg", "broken bones"), ("hay fever", "hay fever"),
    ("blind", "blindness"), ("going blind", "blindness"), ("blurry vision", "bad eyesight"), ("red eyes", "sore eyes"),
    ("deaf", "deafness"), ("can't hear", "deafness"), ("ringing in my ears", "deafness"), ("ear infection", "earache"),
    ("cystitis", "bladder problems"), ("kidney stone", "kidney stones"), ("sore feet", "sore feet"),
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
    deafness = next(a for a in AILMENTS if a.name == "deafness")
    assert deafness.pattern.search("it helps the deaf") and deafness.pattern.search("cures deafness")  # "deaf*"
    blindness = next(a for a in AILMENTS if a.name == "blindness")
    assert blindness.pattern.search("restored sight to them that have been blind")
    assert not blindness.pattern.search("it may dazzle the eyes, and make them blind")  # a warning, not a cure


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

    ALEHOOF, OR GROUND-IVY.

_Descript._] This well known herb is called by some Cat's-foot, Gill-go-by-ground,
and Haymaids.

_Government and virtues._] It is an herb of Venus, and helps the gout.

    CAMOMILE.

IT is so well known every where, that it is but lost time and labour to
describe it. A decoction made of Camomile takes away all pains and stitches in the side.

    THE ELDER TREE.

I HOLD it needless to write any description of this.

    ROOTS.

_Acanths._ Of bearsbreech, it helps the gout.
"""


def test_build_reads_each_herbs_virtues():
    herbs = build.herbs(BOOK)
    assert [h.name for h in herbs] == ["Water Agrimony", "All-Heal", "Alehoof, or Ground-Ivy", "Camomile", "Elder Tree"]
    assert herbs[0].virtues == ("It is a plant of Jupiter. It helps the yellow-jaundice. It kills worms, and helps the "
                                "cough: It consolidates green wounds. It is good to bring away the dead child.")
    assert herbs[0].planet == "Jupiter" and herbs[1].planet is None
    assert herbs[2].aliases == ["Alehoof", "Ground-Ivy", "Cat's-foot", "Gill-go-by-ground", "Haymaids"]
    assert herbs[3].virtues.endswith("takes away all pains and stitches in the side.") and not herbs[3].headed
    data = build.build(BOOK)
    assert [r["text"] for r in data["remedies"]["worms"]] == ["It kills worms, and helps the cough:"]
    limb = data["remedies"]["missing limb"][0]
    assert limb["text"][slice(*limb["match"])] == "consolidates"  # bolded to the end of the word
    assert not any("dead child" in r["text"] for found in data["remedies"].values() for r in found)
    assert data["allheal"][0]["herb"] == "All-Heal"


def test_build_lists_each_herb_with_what_it_treats():
    data = build.build(BOOK, {"_about": "notes", "Alehoof": "Glechoma hederacea", "Water Agrimony": "Bidens"})
    herbs = {h["name"]: h for h in data["herbs"]}
    alehoof = herbs["Alehoof, or Ground-Ivy"]
    assert alehoof["latin"] == "Glechoma hederacea"  # keyed by the start of the name
    assert alehoof["planet"] == "Venus" and alehoof["treats"] == ["gout"]
    assert herbs["Water Agrimony"]["latin"] == "Bidens" and "worms" in herbs["Water Agrimony"]["treats"]
    assert herbs["All-Heal"]["latin"] is None
    assert "aches and pains" in herbs["Camomile"]["treats"]
    assert "Elder Tree" not in herbs  # well known, and only points on to the next herb


def test_latin_names_are_keyed_by_the_start_of_the_name():
    latin = {"Water": "wrong", "Water Agrimony": "Bidens tripartita", "Oak": "Quercus robur"}
    assert build.latin_name("Water Agrimony", latin) == "Bidens tripartita"
    assert build.latin_name("Oak", latin) == "Quercus robur" and build.latin_name("Oaks", latin) is None


def test_every_herbs_latin_name_is_used():
    latin = json.loads(build.LATIN.read_text(encoding="utf-8"))
    used = {h["latin"] for h in cure.data["herbs"]}
    assert [k for k, v in latin.items() if not k.startswith("_") and v not in used] == []


@pytest.mark.parametrize("typed, herb", [
    ("ground ivy", "Alehoof, or Ground-Ivy"), ("Glechoma hederacea", "Alehoof, or Ground-Ivy"),
    ("piss a beds", "Dandelion, vulgarly called Piss-A-Beds"), ("rosemarry", "Rosemary"), ("daisy", "Daisies"),
    ("chamomile", "Camomile"), ("foxglove", "Fox-Glove"), ("digitalis", "Fox-Glove"), ("cannabis", "Hemp"),
    ("bugloss", "Borage and Bugloss"), ("st johns wort", "St. John's Wort"),
])
def test_finds_plants_by_any_name(typed, herb):
    assert lookup.find_herb(typed, cure.herb_entries).herb["name"] == herb


@pytest.mark.parametrize("typed", ["dave", "", "xyzzy plugh"])
def test_no_plant_for_nonsense(typed):
    assert lookup.find_herb(typed, cure.herb_entries) is None


def test_plant_embed(monkeypatch):
    monkeypatch.setattr(cure.random, "choice", lambda options: options[0])
    embed = cure.plant_embed("ground ivy")
    assert embed.title == "🌿 Alehoof, or Ground-Ivy" and embed.footer.text == "Culpeper's Complete Herbal (1653)"
    lines = embed.description.split("\n")
    assert lines[:3] == ["*Glechoma hederacea*", "♀ Governed by Venus",
                         "Also called Cat's-foot, Gill-go-by-ground, Gill-creep-by-ground, Turn-hoof, Haymaids"]
    assert lines[4].startswith("**Good for:** ") and "gout" in lines[4] and lines[5].startswith("> ")
    assert "Also called St John" not in cure.plant_embed("st johns wort").description  # same as the title
    assert cure.plant_embed("dave").description == "Culpeper never wrote about *dave*, not by that name anyway."
    assert cure.plant_embed("sweet maudlin").description.endswith("Nothing on /cure's list, it turns out.")


def test_plant_command_and_autocomplete():
    ctx = Ctx(User(1, "scott"))
    run(cure.plant.callback(ctx, name="sage"))
    assert ctx.last.embed.title == "🌿 Sage"
    choices = [c.value for c in run(cure.plant_autocomplete(types.SimpleNamespace(), "glech"))]
    assert choices == ["Glechoma hederacea"]
    assert len(run(cure.plant_autocomplete(types.SimpleNamespace(), ""))) == 25


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
