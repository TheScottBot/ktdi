"""/magicsquare: Agrippa's planetary squares, made-to-order ones and SATOR (ktdi.features.magicsquare)."""

import random
import types

import pytest

from ktdi.features import magicsquare as squares
from tests.fakes import Ctx, User, run

SCOTT = User(1, "scott")

# Agrippa's tables, as Wikipedia's "Magic square" gives them (the Table of Jupiter is also on Plate X of /talisman's
# Pavitt): the first two rows of each
AGRIPPA_FIRST_ROWS = {
    "Saturn": [4, 9, 2],
    "Jupiter": [4, 14, 15, 1],
    "Mars": [11, 24, 7, 20, 3],
    "Sun": [6, 32, 3, 34, 35, 1],
    "Venus": [22, 47, 16, 41, 10, 35, 4],
    "Mercury": [8, 58, 59, 5, 4, 62, 63, 1],
    "Moon": [37, 78, 29, 70, 21, 62, 13, 54, 5],
}
AGRIPPA_SECOND_ROWS = {
    "Saturn": [3, 5, 7],
    "Jupiter": [9, 7, 6, 12],
    "Mars": [4, 12, 25, 8, 16],
    "Sun": [7, 11, 27, 28, 8, 30],
    "Venus": [5, 23, 48, 17, 42, 11, 29],
    "Mercury": [49, 15, 14, 52, 53, 11, 10, 56],
    "Moon": [6, 38, 79, 30, 71, 22, 63, 14, 46],
}
# The intelligence and spirit of each, spelt as the 1651 English translation of book II, chapter 22 has them
AGRIPPA_NAMES = {
    "Saturn": ("Agiel", "Zazel"), "Jupiter": ("Johphiel", "Hismael"), "Mars": ("Graphiel", "Barzabel"),
    "Sun": ("Nachiel", "Sorath"), "Venus": ("Hagiel", "Kedemel"), "Mercury": ("Tiriel", "Taphthartharath"),
    "Moon": ("Malcha betharsism hed beruah schehalim", "Hasmodai"),
}
SATURN = [[4, 9, 2], [3, 5, 7], [8, 1, 6]]
JUPITER = [[4, 14, 15, 1], [9, 7, 6, 12], [5, 11, 10, 8], [16, 2, 3, 13]]
MARS = [[11, 24, 7, 20, 3], [4, 12, 25, 8, 16], [17, 5, 13, 21, 9], [10, 18, 1, 14, 22], [23, 6, 19, 2, 15]]


@pytest.fixture(autouse=True)
def seeded():
    random.seed(7)


def planet(name: str) -> dict:
    return next(p for p in squares.PLANETS if p["planet"] == name)


# --- The squares ---
@pytest.mark.parametrize("n", range(3, squares.LARGEST + 1))
def test_every_size_is_magic_however_its_turned(n):
    assert squares.is_magic(squares.magic_square(n))
    assert all(squares.is_magic(squares.shuffled(squares.magic_square(n))) for _ in range(8))


def test_the_recipes_give_agrippas_own_squares():
    assert planet("Saturn")["grid"] == SATURN and planet("Jupiter")["grid"] == JUPITER
    assert planet("Mars")["grid"] == MARS
    for name, first_row in AGRIPPA_FIRST_ROWS.items():
        assert planet(name)["grid"][:2] == [first_row, AGRIPPA_SECOND_ROWS[name]], name
        assert squares.is_magic(planet(name)["grid"]), name
        assert (planet(name)["intelligence"], planet(name)["spirit"]) == AGRIPPA_NAMES[name], name


def test_is_magic_isnt_fooled():
    assert not squares.is_magic([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
    assert not squares.is_magic([[5, 5, 5], [5, 5, 5], [5, 5, 5]])  # Every line adds to 15, but it's not 1 to 9


def test_the_sun_adds_up_to_666():
    assert sum(sum(row) for row in planet("Sun")["grid"]) == 666 and squares.magic_sum(6) == 111


def test_sator_reads_the_same_four_ways():
    words = squares.SATOR_WORDS
    assert words == ["".join(column) for column in zip(*words)]  # Down
    assert words == [word[::-1] for word in words][::-1]  # Backwards, from the bottom


# --- The command ---
def test_a_planet_by_any_of_its_names():
    for asked in ("saturn", "Saturday", "lead", "zazel", "3", "3x3", "lo shu"):
        assert squares.squares_embed(asked).title == "🔢 The Square of Saturn", asked
    embed = squares.squares_embed("the sun")
    assert embed.title == "🔢 The Square of the Sun"
    assert embed.description.startswith("```\n 6 32  3 34 35  1\n")
    assert [f.value for f in embed.fields][:4] == ["111", "666", "Sunday", "A golden plate"]
    assert embed.footer.text.startswith("Agrippa, De occulta philosophia (1533)")


def test_sator():
    embed = squares.squares_embed("sator")
    assert embed.title == "🔤 The SATOR Square"
    assert embed.description.startswith("```\nS A T O R\nA R E P O\nT E N E T\nO P E R A\nR O T A S\n```")
    assert "Pompeii" in embed.description and squares.squares_embed("rotas").title == embed.title


def test_sizes_with_no_planet():
    embed = squares.squares_embed("10")
    assert embed.title == "🔢 A 10×10 magic square" and embed.fields[0].value == "505"
    numbers = [[int(n) for n in line.split()] for line in embed.description.split("```")[1].strip().split("\n")]
    assert squares.is_magic(numbers)
    assert "Technically" in squares.squares_embed("1").description
    assert "no 2×2" in squares.squares_embed("2").description
    assert squares.squares_embed("13").title == "🔢 Too big"


def test_random_and_nothing():
    assert squares.squares_embed(None).title.startswith(("🔢 The Square", "🔤 The SATOR"))
    assert "No magic square for that" in squares.squares_embed("zzqx").description


def test_command_alias_and_autocomplete():
    ctx = Ctx(SCOTT)
    run(squares.magicsquare.callback(ctx, which="venus"))
    assert ctx.last.embed.title == "🔢 The Square of Venus"
    ctx = Ctx(SCOTT)
    ctx.invoked_with = "sator"
    run(squares.magicsquare.callback(ctx, which=None))
    assert ctx.last.embed.title == "🔤 The SATOR Square"
    assert "Tiriel" in [c.value for c in run(squares.which_autocomplete(types.SimpleNamespace(), "tiri"))]
    assert squares.magicsquare.aliases == ["magicsquares", "kamea", "sator"]


def test_lore_finds_it_on_the_esoteric_shelf():
    from ktdi.features import lore
    assert any(book.command == "magicsquare" for book, _ in lore.searched("saturn", "esoteric"))
