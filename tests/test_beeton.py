"""/beeton: Mrs Beeton's recipes and household advice (ktdi.features.beeton, ktdi.tools.beeton_build)."""

import json
from datetime import date
import types

import pytest

from ktdi.features import beeton
from ktdi.tools import beeton_build as build, gutenberg
from tests.fakes import Ctx, User, run

SCOTT = User(1, "scott")

BOOK = """Contents, and the index.


CHAPTER I.

THE MISTRESS.

1. As with the commander of an army, so is it with the mistress of a house.

3. EARLY RISING IS ONE OF THE MOST ESSENTIAL QUALITIES which enter into good Household Management, as it is not
only the parent of health, but of innumerable other advantages.

4. Short.


CHAPTER VI.

FRUIT AND VEGETABLE SOUPS.

ALMOND SOUP.

110. INGREDIENTS.--4 lbs. of lean beef or veal, 1/2 lb. of sweet almonds, the
yolks of 6 eggs, rather more than 2 quarts of water, stock No.
105.

_Mode_.--Boil the beef, or veal, gently in water that will cover them, till
the gravy is very strong.

Pound the almonds till they are a mere pulp.

_Time_.--3 hours. _Average cost_ per quart, 2s. 3d.

_Seasonable_ all the year.

_Sufficient_ for 8 persons.

[Illustration: ALMOND & BLOSSOM.]

    THE ALMOND-TREE.--This tree is indigenous to the northern parts
    of Asia and Africa.

LEEK SOUP.

I.

133. INGREDIENTS.--A sheep's head, 12 leeks cut small.

_Mode_.--Prepare the head, and simmer very gently for 4 hours.

_Time_.--4-1/2 hours. _Average cost_, 4d. per quart.


II.

COMMONLY CALLED COCK-A-LEEKIE.

134. INGREDIENTS.--A capon or large fowl, 2 or 3 bunches of fine leeks.

_Mode_.-=Boil the leeks and the fowl together.


II.

_(More Economical.)_

135. INGREDIENTS.--Leeks, water.

_Mode_.--Boil the leeks.

YORKSHIRE PUDDING, to serve with hot Roast Beef.


1384. INGREDIENTS.--1-1/2 pint of milk, 6 _large_ tablespoonfuls of flour, 3 eggs.

[Illustration: YORKSHIRE PUDDING.]

_Mode_.--Put the flour into a basin with the salt, and stir gradually to this enough milk to make a stiff batter.

_Time_.--1-1/2 hour. _Average cost_, 7d.


CHAPTER XL.

DINNERS AND DINING.

1879. Man, it has been said, is a dining animal, and dinner the great event of the day.

DESSERT.

PLAIN FAMILY DINNERS FOR OCTOBER.

2081. _Sunday_.--1. Roast sucking-pig, tomata sauce and brain sauce;
small boiled leg of mutton, caper sauce. 2. Damson tart, boiled batter pudding.

2088. _Sunday_.--1. Crimped cod and oyster sauce. 2. Roast haunch of
mutton. 3. Bullace pudding, baked custards in cups.

2089. _Monday_.--1. The remains of codfish, flaked. 2. Cold mutton and salad. 3. Arrowroot blancmange and stewed
damsons. 2090. _Tuesday_.--1. Roast hare, gravy, and red-currant jelly. 2. Currant dumplings.


CHAPTER XLIII.

THE DOCTOR.

2578. "Time," according to the old proverb, "is money;" and it may also be said to be health.

*** END OF THE PROJECT GUTENBERG EBOOK
"""


@pytest.fixture(autouse=True)
def entries(monkeypatch):
    found = build.entries(BOOK)
    monkeypatch.setattr(beeton, "RECIPES", beeton.recipes(found))
    monkeypatch.setattr(beeton, "ADVICE", beeton.advice(found))
    monkeypatch.setattr(beeton, "MENUS", [e for e in found if e["kind"] == "menu"])
    monkeypatch.setattr(beeton, "today", lambda: date(2026, 10, 11))  # A Sunday in October
    monkeypatch.setattr(beeton.random, "choice", lambda options: options[0])
    monkeypatch.setattr(beeton.random, "sample", lambda options, n: list(options)[:n])


# --- Reading the book ---
def test_numbered_sections_take_their_headings_from_the_lines_above():
    sections = gutenberg.numbered_sections("ALMOND SOUP.\n\n110. INGREDIENTS.--Almonds, stock No.\n105.\n\n"
                                           "[Illustration: ALMONDS.]\n\nLEEK SOUP.\n\n(_Economical_.)\n\n133. Leeks.")
    assert sections == [  # "No.\n105." isn't a section: numbers start paragraphs
        {"number": 110, "headings": ["ALMOND SOUP."], "text": "INGREDIENTS.--Almonds, stock No.\n105."},
        {"number": 133, "headings": ["LEEK SOUP.", "(_Economical_.)"], "text": "Leeks."},
    ]


def test_recipes_and_advice_are_read_from_the_book():
    found = {e["number"]: e for e in build.entries(BOOK)}
    # Advice from the house chapters only (not the doctor's), and nothing too short to be worth reading.
    assert sorted(found) == [1, 3, 110, 133, 134, 135, 1384, 1879, 2081, 2088, 2089, 2090]
    soup = found[110]
    assert soup["name"] == "Almond Soup" and soup["subtitle"] is None
    assert soup["ingredients"] == ("4 lbs. of lean beef or veal, 1/2 lb. of sweet almonds, the yolks of 6 eggs, rather "
                                   "more than 2 quarts of water, stock No. 105.")
    assert soup["method"] == ("Boil the beef, or veal, gently in water that will cover them, till the gravy is very "
                              "strong.\n\nPound the almonds till they are a mere pulp.")
    assert (soup["time"], soup["cost"], soup["seasonable"], soup["serves"]) == \
        ("3 hours", "per quart, 2s. 3d", "all the year", "for 8 persons")
    assert soup["aside"] == "THE ALMOND-TREE.--This tree is indigenous to the northern parts of Asia and Africa."
    assert found[133]["name"] == "Leek Soup I"
    assert found[134]["name"] == "Cock-a-Leekie II"  # "COMMONLY CALLED", the second version
    assert (found[135]["name"], found[135]["subtitle"]) == ("Cock-a-Leekie II", "More Economical")
    assert (found[1384]["name"], found[1384]["subtitle"]) == ("Yorkshire Pudding", "To serve with hot Roast Beef")
    assert found[3]["name"] == "Early rising is one of the most essential qualities"
    assert found[3]["text"].startswith("Early rising is one of the most essential qualities which enter")


def test_build_keeps_the_allowlist_and_drops_left_out_asides():
    kept = build.build(BOOK, {"keep": [110, 133, 3], "no_aside": [110]})["entries"]
    assert [e["number"] for e in kept] == [3, 110, 133]
    assert kept[1]["aside"] is None  # The recipe stays; its aside doesn't


def test_the_real_data_is_exactly_whats_on_the_allowlist():
    curation = json.loads(build.CURATION.read_text(encoding="utf-8"))
    assert set(curation) == {"_about", "keep", "no_aside"}  # Numbers only: nothing records what was said
    real = json.loads(beeton.DATA.read_text(encoding="utf-8"))["entries"]
    assert [e["number"] for e in real] == curation["keep"]
    assert sum(e["kind"] == "recipe" for e in real) >= 1000 and sum(e["kind"] == "advice" for e in real) >= 300
    dinners = [(e["month"], e["day"]) for e in real if e["kind"] == "menu"]
    assert len(dinners) == 168 and all(dinners.count(d) == 2 for d in dinners)  # A fortnight a month: two per weekday
    for entry in real:
        if entry["kind"] == "menu":
            assert 1 <= len(entry["courses"]) <= 4 and all(c.strip() for c in entry["courses"]), entry["number"]
            continue
        assert entry["name"].strip(), entry["number"]
        if entry["number"] in curation["no_aside"]:
            assert entry["aside"] is None, entry["number"]
        assert "#:~:text=" in beeton.url(entry), entry["number"]


# --- Recipes ---
def test_a_recipe_by_name():
    embed = beeton.recipe("almond soup")
    assert embed.title == "🍽️ Almond Soup"
    assert embed.description.startswith("Boil the beef, or veal, gently in water")
    assert ("⏱️ 3 hours · 💷 per quart, 2s. 3d (about £17 now) · 🍽️ for 8 persons · 📅 all the year"
            in embed.description)  # Her cost, and what it'd be now
    assert "-# 📖 THE ALMOND-TREE.—This tree is indigenous" in embed.description
    assert embed.fields[0].name == "Ingredients" and embed.fields[0].value.startswith("4 lbs. of lean beef")
    assert embed.footer.text == beeton.SOURCE
    assert embed.url.startswith("https://www.gutenberg.org/cache/epub/10136/pg10136-images.html#:~:text=Boil%20the")


def test_a_recipe_by_ingredient_names_the_others():
    embed = beeton.recipe("leeks")
    assert embed.title == "🍽️ Leek Soup I"
    also = embed.fields[1]
    assert also.name == "Also with “leeks”" and also.value == "Cock-a-Leekie II · Cock-a-Leekie II"


def test_subtitles_and_typos():
    assert beeton.recipe("yorkshire pudding").description.startswith("*To serve with hot Roast Beef*\n\n")
    assert beeton.recipe("yorkshre puding").title == "🍽️ Yorkshire Pudding"


def test_random_and_nothing():
    assert beeton.recipe(None).title == "🍽️ Almond Soup"
    assert "No recipe for that here" in beeton.recipe("zzqx").description


# --- Advice ---
def test_advice():
    embed = beeton.household("early rising")
    assert embed.title == "🏠 Early rising is one of the most essential qualities"
    assert embed.footer.text == beeton.SOURCE  # Only the one passage
    assert beeton.household(None).title.startswith("🏠 As with the commander of an army")
    assert "Nothing from Mrs Beeton on that here" in beeton.household("zzqx").description


def test_commands():
    ctx = Ctx(SCOTT)
    run(beeton.beeton.callback(ctx, dish="almond soup"))
    assert ctx.last.embed.title == "🍽️ Almond Soup"
    run(beeton.beeton_advice.callback(ctx, topic="early rising"))
    assert ctx.last.embed.title.startswith("🏠 Early rising")
    choices = run(beeton.dish_autocomplete(types.SimpleNamespace(), "leek"))
    assert [c.value for c in choices] == ["Leek Soup I", "Cock-a-Leekie II"]


# --- Menus ---
def test_family_dinners_are_read_from_the_book():
    found = {e["number"]: e for e in build.entries(BOOK)}
    sunday = found[2081]
    assert (sunday["kind"], sunday["month"], sunday["day"]) == ("menu", 10, "Sunday")
    assert sunday["courses"] == ["Roast sucking-pig, tomata sauce and brain sauce; small boiled leg of mutton, caper "
                                 "sauce.", "Damson tart, boiled batter pudding."]
    # Tuesday runs on in Monday's paragraph in the book; it's split off with its own number.
    assert found[2089]["courses"][-1] == "Arrowroot blancmange and stewed damsons."
    assert (found[2090]["day"], found[2090]["courses"]) == (
        "Tuesday", ["Roast hare, gravy, and red-currant jelly.", "Currant dumplings."])
    assert found[1879]["kind"] == "advice"  # The chapter's other paragraphs are still advice


def test_which_day_to_dine_on():
    sunday = date(2026, 10, 11)
    assert beeton.menu_day(None, sunday) == (10, 6)  # Today: October, a Sunday
    assert beeton.menu_day("friday", sunday) == (10, 4)  # That weekday, this month
    assert beeton.menu_day("Tues", sunday) == (10, 1) and beeton.menu_day("mondays", sunday) == (10, 0)
    assert beeton.menu_day("25/12", sunday) == (12, 4)  # Christmas 2026 is a Friday
    assert beeton.menu_day("tomorrow", sunday) == (10, 0)


def test_the_menu():
    embed = beeton.menu(None)
    assert embed.title == "🍽️ Dinner for a Sunday in October"
    assert embed.description == ("**1.** Roast sucking-pig, tomata sauce and brain sauce; small boiled leg of "
                                 "mutton, caper sauce.\n**2.** Damson tart, boiled batter pudding.")
    assert embed.footer.text == f"Plain family dinners, {beeton.SOURCE}. Ask again for her other one."
    assert beeton.menu("tuesday").title == "🍽️ Dinner for a Tuesday in October"
    assert beeton.menu("tuesday").footer.text == f"Plain family dinners, {beeton.SOURCE}."  # Only the one here
    assert "needs a weekday (friday) or a date" in beeton.menu("blah").description
    assert "no 29 February this year" in beeton.menu("29 feb").description


def test_menu_command():
    ctx = Ctx(SCOTT)
    run(beeton.beeton_menu.callback(ctx, day="monday"))
    assert ctx.last.embed.title == "🍽️ Dinner for a Monday in October"
    assert beeton.beeton_menu.aliases == ["dinner"]
