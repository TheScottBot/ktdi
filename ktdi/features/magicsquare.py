"""/magicsquare [which]: a magic square, drawn in the chat. Every row, column and both diagonals add up the same.

The seven planetary squares are Cornelius Agrippa's, from book II, chapter 22 of his De occulta philosophia (1533):
the Square of Saturn (3×3) to the Square of the Moon (9×9), each with the planet's day, what he says to engrave it
on, and the intelligence and spirit he gives it. They're worked out here, not copied: his odd squares all follow one
pattern (odd_square), and his 4×4 and 8×8 another (doubly_even_square); the Sun's 6×6 follows neither, so it's
written out (SUN). tests/test_magicsquare.py checks them against his tables. Any other size up to LARGEST is made
fresh each time (magic_square), turned and flipped at random.

The SATOR square is the Latin word square the Romans scratched on walls from Pompeii to Cirencester, which reads the
same four ways. The notes are ours, nothing is quoted, so there's nothing to curate; every claim in them is from one
of these (checked October 2026):
- Agrippa, Three Books of Occult Philosophy, book II ch. 22, in the 1651 English translation (Peterson's
  transcription, esotericarchives.com/agrippa/op2.htm): the sums and totals (666 for the Sun), the names, what to
  engrave each table on, the order Saturn to Moon, the pigeons;
- Wikipedia, "Magic square": the seven squares themselves; "Luoshu Square": the turtle of the River Luo;
  "Names of the days of the week": the planetary days;
- MathWorld, "Dürer's Magic Square", and the National Gallery of Art: Melencolia I (1514) and the 15 14;
- Founders Online, James Logan to Benjamin Franklin (1750) and Franklin to Peter Collinson (1752): Franklin's
  squares, made as clerk of the Pennsylvania Assembly;
- Wikipedia, "Sator Square", and Roman Inscriptions of Britain 2447.20: Pompeii (1925, 1936, both ROTAS),
  Cirencester (1868), Dura-Europos, the PATER NOSTER anagram (three people, 1924–26), the fire charms, Tenet.

It's an old book in all but name, so it declares OLD_BOOK: /lore and the esoteric shelf ask it (`/lore saturn`),
and Old Wisdom of the Day can post a square.
"""

import random
import re

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import oldbooks

HELP_CATEGORY = "🐉 Beasts & magic"
EMOJI = "🔢"
COLOUR = discord.Color.from_rgb(212, 175, 55)  # Gold
LARGEST = 12  # Bigger than this and the grid is more scrolling than square
SOURCE = "Agrippa's planetary squares (1533) and the Roman SATOR square"
AGRIPPA = "Agrippa, De occulta philosophia (1533), book II: the tables of the planets"


def odd_square(n: int) -> list[list[int]]:
    """Agrippa's way with an odd square: 1 just below the middle, then each next number one step down and to the right
    (off one edge and back on the other), or two steps down if that cell's taken."""
    grid = [[0] * n for _ in range(n)]
    row, col = (n // 2 + 1) % n, n // 2
    for number in range(1, n * n + 1):
        grid[row][col] = number
        down, right = (row + 1) % n, (col + 1) % n
        row, col = (down, right) if not grid[down][right] else ((row + 2) % n, col)
    return grid


def doubly_even_square(n: int) -> list[list[int]]:
    """Agrippa's way with a square of 4, 8, 12...: the numbers in order, each one that isn't on a diagonal of its 4×4
    block swapped for its opposite (n² + 1 - it), and every row read right to left."""
    def place(i: int, j: int) -> int:
        number = i * n + j + 1
        return number if (i % 4 in (0, 3)) == (j % 4 in (0, 3)) else n * n + 1 - number
    return [[place(i, j) for j in range(n)][::-1] for i in range(n)]


def singly_even_square(n: int) -> list[list[int]]:
    """A square of 6, 10...: Strachey's method. Four odd squares in quarters, numbered one after another, then a few
    columns swapped between the top and bottom halves to even out the sums."""
    half, k = n // 2, (n - 2) // 4
    quarter, area = odd_square(half), half * half
    grid = [[0] * n for _ in range(n)]
    for i in range(half):
        for j in range(half):
            grid[i][j], grid[i + half][j + half] = quarter[i][j], quarter[i][j] + area
            grid[i][j + half], grid[i + half][j] = quarter[i][j] + 2 * area, quarter[i][j] + 3 * area
    for i in range(half):
        columns = list(range(1, k + 1) if i == half // 2 else range(k)) + list(range(n - k + 1, n))
        for j in columns:
            grid[i][j], grid[i + half][j] = grid[i + half][j], grid[i][j]
    return grid


def magic_square(n: int) -> list[list[int]]:
    """A magic square of any size from 3, by the recipe for its kind."""
    if n % 2:
        return odd_square(n)
    return doubly_even_square(n) if n % 4 == 0 else singly_even_square(n)


def shuffled(grid: list[list[int]]) -> list[list[int]]:
    """The same square turned, flipped, or with every number swapped for its opposite: still magic, but fresh."""
    for _ in range(random.randrange(4)):
        grid = [list(row) for row in zip(*grid[::-1])]  # A quarter turn
    if random.random() < 0.5:
        grid = [row[::-1] for row in grid]
    if random.random() < 0.5:
        top = len(grid) ** 2 + 1
        grid = [[top - number for number in row] for row in grid]
    return grid


def magic_sum(n: int) -> int:
    """What every row, column and diagonal of an n×n magic square adds up to."""
    return n * (n * n + 1) // 2


def is_magic(grid: list[list[int]]) -> bool:
    """Whether it's a magic square: 1 to n² once each, every line adding up the same."""
    n, target = len(grid), magic_sum(len(grid))
    lines = [*grid, *zip(*grid), [grid[i][i] for i in range(n)], [grid[i][n - 1 - i] for i in range(n)]]
    return sorted(x for row in grid for x in row) == list(range(1, n * n + 1)) and all(sum(l) == target for l in lines)


# The Sun's 6×6, as Agrippa gives it: the one of his seven the recipes don't build
SUN = [[6, 32, 3, 34, 35, 1], [7, 11, 27, 28, 8, 30], [19, 14, 16, 15, 23, 24], [18, 20, 22, 21, 17, 13],
       [25, 29, 10, 9, 26, 12], [36, 5, 33, 4, 2, 31]]

# Agrippa's seven, from book II, chapter 22 (in the 1651 English translation): the intelligence and spirit he names
# for each, spelt as he does, and what he says to engrave the table on. The days are the planetary week's.
PLANETS = [
    {"planet": "Saturn", "size": 3, "day": "Saturday", "engraved": "a plate of lead", "metals": ["lead"],
     "intelligence": "Agiel", "spirit": "Zazel",
     "note": "The smallest. The same square is China's Lo Shu, which legend says appeared on the shell of a turtle "
             "that came out of the River Luo.", "also": ["lo shu", "3x3"]},
    {"planet": "Jupiter", "size": 4, "day": "Thursday", "engraved": "a silver plate", "metals": ["silver"],
     "intelligence": "Johphiel", "spirit": "Hismael",
     "note": "The Table of Jupiter. Albrecht Dürer put a different 4×4 square in his engraving Melencolia I (1514), "
             "with the year, 15 14, in the middle of its bottom row.",
     "also": ["table of jupiter", "iophiel", "4x4"]},
    {"planet": "Mars", "size": 5, "day": "Tuesday", "engraved": "an iron plate, or a sword", "metals": ["iron"],
     "intelligence": "Graphiel", "spirit": "Barzabel",
     "note": "Agrippa's odd squares all follow one pattern: 1 just below the middle, then each next number one step "
             "diagonally down and to the right (off one edge, back on the other), or two rows down if that cell's "
             "taken.", "also": ["5x5"]},
    {"planet": "Sun", "size": 6, "day": "Sunday", "engraved": "a golden plate", "metals": ["gold"],
     "intelligence": "Nachiel", "spirit": "Sorath",
     "note": "Agrippa points out that its 36 numbers add up to 666. It's the one of his seven the bot can't build "
             "from a pattern, so his table is copied as it is.", "also": ["sol", "6x6", "666"]},
    {"planet": "Venus", "size": 7, "day": "Friday", "engraved": "a silver plate", "metals": ["silver"],
     "intelligence": "Hagiel", "spirit": "Kedemel",
     "note": "Agrippa says that, engraved on silver and put into a dove-house, it causes an increase of pigeons.",
     "also": ["7x7", "pigeons"]},
    {"planet": "Mercury", "size": 8, "day": "Wednesday", "engraved": "silver, tin or yellow brass, or virgin "
     "parchment", "metals": ["silver", "tin", "brass"], "intelligence": "Tiriel", "spirit": "Taphthartharath",
     "note": "A chessboard of numbers. Benjamin Franklin made 8×8 squares of his own in the 1730s, to pass the "
             "time as clerk of the Pennsylvania Assembly.", "also": ["8x8"]},
    {"planet": "Moon", "size": 9, "day": "Monday", "engraved": "silver", "metals": ["silver"],
     "intelligence": "Malcha betharsism hed beruah schehalim", "spirit": "Hasmodai",
     "note": "The last and largest: Agrippa's tables run from Saturn's 3×3 to the Moon's 9×9, one size bigger each "
             "time. He gives the Moon a spirit of its spirits, too: Schedbarschemoth Scharthathan.",
     "also": ["luna", "9x9", "chasmodai", "schedbarschemoth scharthathan"]},
]
for planet in PLANETS:
    planet["title"] = f"The Square of {'the ' if planet['planet'] in ('Sun', 'Moon') else ''}{planet['planet']}"
    planet["grid"] = SUN if planet["size"] == 6 else magic_square(planet["size"])
    planet["text"] = (f"A {planet['size']}×{planet['size']} magic square: every row, column and diagonal adds up to "
                      f"{magic_sum(planet['size'])}. Day: {planet['day']}. Engraved on {planet['engraved']}. "
                      f"Intelligence: {planet['intelligence']}. Spirit: {planet['spirit']}. {planet['note']}")

SATOR_WORDS = ["SATOR", "AREPO", "TENET", "OPERA", "ROTAS"]
SATOR = {
    "title": "The SATOR Square", "also": ["rotas", "arepo", "tenet", "opera", "paternoster", "pompeii",
                                           "cirencester", "word square"],
    "text": "SATOR AREPO TENET OPERA ROTAS: a Latin word square that reads the same across, down, backwards and up. "
            "Roughly, \"The sower Arepo holds the wheels with care\"; nobody knows who or what Arepo was. Two were "
            "scratched on walls at Pompeii, buried in AD 79 (both the older form, starting ROTAS), and one on wall "
            "plaster at Cirencester in Roman Britain; more turned up at Dura-Europos in Syria. In the 1920s three "
            "people noticed, separately, that its letters make PATER NOSTER twice, crossing at the N, with an A and "
            "an O (alpha and omega) left at each end, which may or may not be the point. It was written on charms "
            "against fire for centuries after, and in 2020 Christopher Nolan took the film Tenet's title, and its "
            "Sator, Arepo and Rotas, from it, and opened the film at an opera.",
}
SQUARES = PLANETS + [SATOR]


def names(square: dict) -> list[str]:
    if square is SATOR:
        return [square["title"], "sator", *square["also"]]
    return [square["title"], square["planet"], square["day"], *square["metals"], square["intelligence"],
            square["spirit"], *square["also"]]


DICTIONARY = oldbooks.Dictionary(SQUARES, names=names, text=lambda s: f"{s['title']}. {s['text']}", close_first=True)


def drawn(grid: list[list[int]]) -> str:
    """A square of numbers as a code block, each column lined up."""
    width = len(str(len(grid) ** 2))
    return "```\n" + "\n".join(" ".join(str(n).rjust(width) for n in row) for row in grid) + "\n```"


def planet_embed(square: dict) -> discord.Embed:
    n = square["size"]
    embed = discord.Embed(title=f"{EMOJI} {square['title']}", color=COLOUR,
                          description=f"{drawn(square['grid'])}\n{square['note']}")
    embed.add_field(name="Every line adds to", value=str(magic_sum(n)))
    embed.add_field(name="All of them", value=f"{n * n * (n * n + 1) // 2:,}")
    embed.add_field(name="Day", value=square["day"])
    embed.add_field(name="Engrave it on", value=square["engraved"][:1].upper() + square["engraved"][1:])
    embed.add_field(name="Intelligence and spirit", value=f"{square['intelligence']} and {square['spirit']}",
                    inline=False)
    embed.set_footer(text=f"{AGRIPPA}. Every row, column and both diagonals add up the same.")
    return embed


def sator_embed() -> discord.Embed:
    grid = "```\n" + "\n".join(" ".join(word) for word in SATOR_WORDS) + "\n```"
    embed = discord.Embed(title="🔤 The SATOR Square", color=COLOUR, description=grid + "\n" + SATOR["text"])
    embed.set_footer(text="Roman, 1st century AD and after. Read it across, down, backwards or up: it's the same.")
    return embed


def made_embed(n: int) -> discord.Embed:
    """A square no planet has, made just now."""
    embed = discord.Embed(title=f"{EMOJI} A {n}×{n} magic square", color=COLOUR,
                          description=f"{drawn(shuffled(magic_square(n)))}\nMade just now: ask again for another.")
    embed.add_field(name="Every line adds to", value=str(magic_sum(n)))
    embed.add_field(name="All of them", value=f"{n * n * (n * n + 1) // 2:,}")
    embed.set_footer(text="No planet has one this size: Agrippa's stop at the Moon's 9×9.")
    return embed


def square_embed(square: dict) -> discord.Embed:
    return sator_embed() if square is SATOR else planet_embed(square)


def squares_embed(which: str | None) -> discord.Embed:
    """The square asked for: a planet's (by planet, day, metal, spirit or size), SATOR, a made one, or any."""
    size = re.fullmatch(r"\s*(\d+)\s*(?:[x×]\s*\d+)?\s*", which or "")
    if size:
        n = int(size[1])
        planet = next((p for p in PLANETS if p["size"] == n), None)
        if planet:
            return planet_embed(planet)
        if n == 1:
            return discord.Embed(title=f"{EMOJI} A 1×1 magic square", description="```\n1\n```\nTechnically.",
                                 color=COLOUR)
        if n == 2:
            return discord.Embed(title=f"{EMOJI} No 2×2", color=COLOUR,
                                 description="There's no 2×2 magic square: try putting 1 to 4 in one and see.")
        if 2 < n <= LARGEST:
            return made_embed(n)
        return discord.Embed(title=f"{EMOJI} Too big", color=COLOUR,
                             description=f"Up to {LARGEST}×{LARGEST}: any bigger and it's more scrolling than square.")
    found = DICTIONARY.one_of(which)
    if not found:
        return discord.Embed(title=f"{EMOJI} {oldbooks.shown_typed(which)}", color=COLOUR,
                             description="No magic square for that. Try a planet (Saturn, the Sun, the Moon), a size "
                                         f"(3 to {LARGEST}), or SATOR.")
    return square_embed(found[0])


@commands.hybrid_command(name="magicsquare", aliases=["magicsquares", "kamea", "sator"],
                         description="A planet's magic square (Agrippa, 1533), any size up to 12, or the SATOR square.")
@app_commands.describe(which="A planet (saturn, sun, moon...), a size (3 to 12) or sator. Empty: any")
async def magicsquare(ctx: commands.Context, *, which: str | None = None):
    """A magic square, drawn in the chat: every row, column and both diagonals add up the same. The seven planetary
    squares are Cornelius Agrippa's (1533), from the Square of Saturn (3×3, adding to 15) to the Square of the Moon
    (9×9, adding to 369), each with its day, what he says to engrave it on, and the intelligence and spirit he
    gives it. Ask by planet (`/magicsquare jupiter`), day (`friday`), metal (`gold`), spirit or size
    (`/magicsquare 5`). Sizes with no planet, 10 to 12, are made fresh each time. `/magicsquare sator` is the Roman SATOR AREPO TENET OPERA ROTAS
    square, which reads the same four ways, and its history. On its own: any of them. Typed, `!sator` goes straight
    to SATOR (`!magicsquares` and `!kamea` work too)."""
    if getattr(ctx, "invoked_with", None) == "sator" and not which:  # !sator
        which = "sator"
    await ctx.send(embed=squares_embed(which))


@magicsquare.autocomplete("which")
async def which_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return DICTIONARY.autocomplete(current)


OLD_BOOK = oldbooks.OldBook(SOURCE, EMOJI, "magicsquare", random=lambda: square_embed(random.choice(SQUARES)),
                            find=lambda topic: DICTIONARY.look_up(topic, close_first=False),
                            shelves=("esoteric",))


async def setup(bot: commands.Bot):
    bot.add_command(magicsquare)
