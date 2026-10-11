"""Build /beeton's recipes and household advice from Mrs Beeton's Book of Household Management (1861), from Project
Gutenberg: python -m ktdi.tools.beeton_build

Every paragraph in the book is numbered. A recipe is one that starts "INGREDIENTS.--", under its title in capitals,
with its _Mode_, _Time_, _Average cost_, _Seasonable_ and _Sufficient_ (and often an aside on where the food comes
from, set in smaller type). Advice is the numbered paragraphs of the chapters on running a house: the mistress, the
housekeeper, the kitchen, dinners and dining, servants, and legal memoranda (not the nursery or the doctor: /cure
has that). Only the paragraphs in ktdi/lib/beeton_curation.json are kept (their numbers): the book was read once,
and anything racist or cruel left out, so it's never in the repo. Writes ktdi/lib/beeton.json. The book is public
domain; it's downloaded each time (about 3 MB).

To add a recipe or some advice, read it in the book first, then add its number to "keep". A recipe whose aside
shouldn't be shown has its number in "no_aside" too.
"""

import re

from ktdi.tools import gutenberg

BOOK = 10136
CURATION = gutenberg.curation_file("beeton")
CHAPTER = re.compile(r"\nCHAPTER ([IVXL]+)\.\n")
ADVICE_CHAPTERS = {"I", "II", "III", "XL", "XLI", "XLIV"}  # The house, not the cooking (or the nursery and doctor)
# A recipe's parts, each "_Name_.--text" or "_Name_ text", up to the next part
PARTS = {"time": "Time", "cost": "Average cost", "seasonable": "Seasonable", "serves": "Sufficient"}
NOT_A_TITLE = re.compile(r"^(?:[IVXL]+\.|RECIPES\.?|\[Illustration.*|CHAPTER .*)$")


def tidy(text: str) -> str:
    """One paragraph on one line."""
    return " ".join(text.split())


SMALL_WORDS = {"a", "an", "and", "of", "the", "in", "with", "to", "for", "or", "la", "le", "au", "aux", "de", "du", "des",
               "en", "on", "at", "as"}


def title_case(text: str) -> str:
    """"FRIED RASHERS OF BACON AND POACHED EGGS" is "Fried Rashers of Bacon and Poached Eggs"; "COCK-A-LEEKIE" is
    "Cock-a-Leekie"."""
    words = re.split(r"(\s+|-)", text.lower())
    shown = [w if i and w in SMALL_WORDS else w[:1].upper() + w[1:] for i, w in enumerate(words)]
    return "".join(shown).replace("'S ", "'s ").replace("’S ", "’s ")


def title(headings: list[str], previous: str | None) -> tuple[str | None, str | None]:
    """A recipe's title and subtitle from the lines above it: "ALMOND SOUP." is Almond Soup; "COMMONLY CALLED
    COCK-A-LEEKIE." is Cock-a-Leekie; "CUCUMBER SOUP (French Recipe)." keeps its brackets; "(_Economical_.)" is a
    subtitle. A second version headed just "II." is the recipe above's, second version."""
    bracketed = [h for h in headings if h.lstrip("_").startswith("(")]  # "(_Economical_.)", "_(More Economical.)_"
    subtitles = [h.strip("_().").strip("_. ") for h in bracketed]
    names = [h for h in headings if h not in bracketed and not NOT_A_TITLE.match(h)]
    numeral = next((h.rstrip(".") for h in headings if re.fullmatch(r"[IVXL]+\.", h)), None)
    if names:
        name = re.sub(r"^COMMONLY CALLED ", "", names[-1]).rstrip(".")
        if same_line := re.match(r"(.+?)\.\s+\((.+)\)$", name):  # "NESSELRODE PUDDING. (_A fashionable..._.)"
            name, subtitles = same_line.group(1), subtitles + [same_line.group(2).strip("_. ")]
        elif same_line := re.match(r"([^a-z]+), ([a-z].*)$", name):  # "YORKSHIRE PUDDING, to serve with hot..."
            name, subtitles = same_line.group(1), subtitles + [same_line.group(2)[0].upper() + same_line.group(2)[1:]]
        bracket = re.search(r"\s*(\([^)]*\))$", name)
        name = title_case(name[:bracket.start()] if bracket else name) + (f" {bracket.group(1)}" if bracket else "")
        name += f" {numeral}" if numeral else ""  # The first of several versions: "LEEK SOUP.", "I."
    elif numeral and previous:
        name = f"{re.sub(r' [IVXL]+$', '', previous)} {numeral}"
    else:
        return None, None
    return name, (subtitles[-1] if subtitles else None)


def part(text: str, name: str) -> str | None:
    """One of a recipe's parts: "_Time_.--3 hours." is "3 hours.", "_Sufficient_ for 8 persons." is "for 8 persons."."""
    match = re.search(rf"_{name}_\.?(?:--)?\s*(.+?)(?=\s*_(?:{'|'.join(PARTS.values())}|Mode)_|\n\s*\n|$)", text, re.S)
    return tidy(match.group(1)).strip(" .,") if match else None


def recipe(section: dict, previous: str | None) -> dict | None:
    text = section["text"]
    name, subtitle = title(section["headings"], previous)
    # "INGREDIENTS.--", and the odd "INGREDIENTS.-" or "_Mode_.-=" typo
    ingredients = re.match(r"INGREDIENTS\.?\s*[-=]{1,2}\s*(.+?)(?=\n\s*\n|_?Mode_?\.|$)", text, re.S)
    mode = re.search(r"_?Mode_?\.?\s*[-=]{1,2}\s*(.+?)(?=\n\s*\n\s*_|\n\s*\n {2,}|\[Illustration|$)", text, re.S)
    if not (name and ingredients and mode):
        return None
    paragraphs = re.split(r"\n\s*\n", mode.group(1).strip())
    aside = [tidy(block) for block in re.split(r"\n\s*\n", text) if block.startswith("    ")]
    return {"kind": "recipe", "number": section["number"], "name": name, "subtitle": subtitle,
            "ingredients": tidy(ingredients.group(1)),
            "method": "\n\n".join(tidy(p) for p in paragraphs), **{key: part(text, label) for key, label in PARTS.items()},
            "aside": aside[0] if aside else None}


def advice(section: dict) -> dict | None:
    """A paragraph of advice, named by the words it starts with in capitals ("EARLY RISING IS ONE OF THE MOST
    ESSENTIAL QUALITIES which enter into...": Early rising)."""
    text = "\n\n".join(tidy(p) for p in re.split(r"\n\s*\n", section["text"]) if p.strip() and not p.startswith("["))
    if len(text) < 40:
        return None
    lead = re.match(r"^((?:[A-Z][A-Z'’,&-]*\s+)*[A-Z][A-Z'’&-]+)\b", text)
    if lead and len(lead.group(1)) >= 4:
        topic = lead.group(1).capitalize()
        text = topic + text[len(lead.group(1)):]
    else:  # No words in capitals: named by how it starts ("Man, it has been said, is a dining animal")
        topic = " ".join(re.split(r"[.;:]", text.replace("_", ""), maxsplit=1)[0].split()[:8]).rstrip(",")
    return {"kind": "advice", "number": section["number"], "name": topic, "text": text}


def entries(book: str) -> list[dict]:
    """Every recipe ({"kind": "recipe", "number", "name", "ingredients", "method", "time", "cost", "seasonable",
    "serves", "aside"}) and paragraph of household advice ({"kind": "advice", "number", "name", "text"})."""
    book = book.replace("\r\n", "\n")
    body = book[book.index("\nCHAPTER I.\n"):book.index(gutenberg.END)]
    parts = CHAPTER.split(body)
    found, previous = [], None
    for chapter, text in zip(parts[1::2], parts[2::2]):
        for section in gutenberg.numbered_sections(text):
            if section["text"].startswith("INGREDIENTS"):
                entry = recipe(section, previous)
                previous = entry["name"] if entry else previous
            elif chapter in ADVICE_CHAPTERS:
                entry = advice(section)
            else:
                entry = None
            if entry:
                found.append(entry)
    return found


def build(book: str, curation: dict) -> dict:
    """The paragraphs on the allowlist; a recipe whose aside was left out ("no_aside") keeps the recipe."""
    kept = gutenberg.kept(entries(book), curation["keep"], key=lambda entry: entry["number"])
    for entry in kept:
        if entry["number"] in set(curation["no_aside"]):
            entry["aside"] = None
    return {"entries": kept}


def main() -> None:
    gutenberg.build_from_allowlist(BOOK, "beeton", entries, build=build, key=lambda entry: entry["number"],
                                   report=lambda data: f" {sum(e['kind'] == 'recipe' for e in data['entries'])} "
                                                       "are recipes.")


if __name__ == "__main__":
    main()
