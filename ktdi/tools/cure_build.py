"""Build /cure's remedies from Culpeper's Complete Herbal (1653), from Project Gutenberg:  python -m ktdi.tools.cure_build

Reads each herb's "Government and virtues" (what it cures, in Culpeper's words), finds the sentences that mention each
ailment in ktdi/lib/ailments.py, and writes ktdi/lib/cures.json (also each herb's names, planet and what it treats,
for /plant, with its Latin name from ktdi/lib/herb_latin.json). Run it again after changing an ailment's `culpeper`
terms or a Latin name. The book is public domain; it's downloaded each time (about 1.5 MB).
"""

import json
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from ktdi.lib.ailments import AILMENTS

SOURCE_URL = "https://www.gutenberg.org/cache/epub/49513/pg49513.txt"
OUTPUT = Path(__file__).resolve().parent.parent / "lib" / "cures.json"
LATIN = OUTPUT.with_name("herb_latin.json")  # Botanical names, checked by hand (for /plant)
# A herb's heading: one or more indented lines in capitals ("    BILBERRIES, CALLED BY SOME WHORTS,\n    AND ...").
HERB_RE = re.compile(r"^(?: {2,}[A-Z][A-Z ,'’\-()&.]+[ \t]*\n)+", re.MULTILINE)
VIRTUES_RE = re.compile(r"_Government and virtues\._\]\s*(.*?)(?=\n\s*\n_[A-Z][a-z]|\Z)", re.IGNORECASE | re.DOTALL)
# A herb's description, place and time paragraphs, which come before what it cures.
NOT_VIRTUES_RE = re.compile(r"_(?:Descript|Place|Time)\._\].*?(?:\n\s*\n|\Z)", re.DOTALL)
HERBAL_ENDS = "Roots"  # The first heading after the herbal: his catalogue of simples
CALLED_RE =re.compile(r"\bcalled,?\s+(?:also\s+|in some \w+\s+|by some\s+|by many\s+)?([A-Z][^.;:()]*)")
NAME_PARTS_RE = re.compile(r",\s*(?:or|and|called(?: by some)?)\s+|\s+or\s+|,\s+", re.IGNORECASE)
PLANET_RE = re.compile(r"\b(Saturn|Jupiter|Mars|Venus|Mercury|the Sun|the Moon)\b")
# Bits of headings and descriptions that look like names but aren't ("CAMPION, WILD", "SCABIOUS, THREE SORTS").
NOT_NAMES = {"the", "it", "and", "some", "wild", "stinking", "wild and stinking", "three sorts", "other dodders",
             "spiked heads of flowers"}
MAX_LENGTH = 350
# A few of the herbal's remedies are for ending pregnancies or delivering stillbirths. Not for a joke command.
LEFT_OUT = re.compile(r"abort|dead child|miscarr|bring away the birth|kill the child|untimely birth", re.IGNORECASE)


@dataclass
class Herb:
    name: str  # As Culpeper titles it: "Alehoof, or Ground-Ivy"
    aliases: list[str]  # Every other name he gives it: "Cat's-foot", "Gill-go-by-ground", "Haymaids"...
    virtues: str  # His "Government and virtues": what it's ruled by and what it cures
    planet: str | None  # "Jupiter": he puts every herb under a planet
    headed: bool = True  # False for the "so well known" ones without a "Government and virtues" heading


def herb_name(header: str) -> str:
    name = re.sub(r"\bOR,", "OR", " ".join(header.replace("’", "'").split()).rstrip(".,")).title()
    name = re.sub(r"\b(Or|Of|The|And|In|With|Called|By|Some|Also|Usually|Known|Name|Vulgarly|More|Properly)\b",
                  lambda m: m.group(1).lower(), name)
    return re.sub(r"^the\s+", "", name.replace("'S", "'s"))


def other_names(name: str, block: str) -> list[str]:
    """The names in the heading ("Alehoof, or Ground-Ivy"), and the ones he lists as "called ..." in the text."""
    found = [part for part in NAME_PARTS_RE.split(name) if part]
    description = block.split("_Government", 1)[0].replace("\n", " ").replace("St. ", "St ")
    for called in CALLED_RE.finditer(description):
        found += [p for p in NAME_PARTS_RE.split(called.group(1)) if p[:1].isupper() and len(p.split()) <= 4]
    found += [half for part in found for half in part.split(" and ")]  # "Borage and Bugloss": either will do
    names, seen = [], set()
    for alias in found:
        alias = re.sub(r"[^\w' -]", "", alias.replace("’", "'")).strip()
        alias = re.sub(r"^(?:[a-z]+ )+|\s+by some$", "", alias)  # "usually known by the name of Pilewort"
        key = alias.lower()
        if alias and key not in seen and key not in NOT_NAMES:
            seen.add(key)
            names.append(alias)
    return names


def herbs(text: str) -> list[Herb]:
    text = text.replace("\r\n", "\n")
    headers = list(HERB_RE.finditer(text))
    found = []
    for header, following in zip(headers, headers[1:] + [None]):
        block = text[header.end():following.start() if following else len(text)]
        name = herb_name(header.group(0))
        if name == HERBAL_ENDS:
            break
        virtues = VIRTUES_RE.search(block)
        if virtues:
            virtues = virtues.group(1)
        elif found:  # Herbs "so well known" (Camomile, Elder) skip the headings and go straight to what they cure.
            described = list(NOT_VIRTUES_RE.finditer(block))
            virtues = block[described[-1].end():] if described else block
        else:
            continue  # The title pages and introduction
        clean = " ".join(virtues.replace("_", "").split())  # Gutenberg marks italics _like this_.
        if not clean:
            continue  # Its virtues are under the next herb's ("They are both under the dominion of Jupiter")
        planet = PLANET_RE.search(clean)
        found.append(Herb(name, other_names(name, block), clean, planet.group(1) if planet else None,
                          headed=VIRTUES_RE.search(block) is not None))
    return found


def sentences(virtues: str) -> list[str]:
    """Culpeper's sentences run on with colons and semicolons; each clause is a remedy of its own."""
    parts = re.split(r"(?<=[.:;!?])\s+(?=[A-Z])", virtues)
    return [p.strip() for p in parts if 4 <= len(p.split()) and not LEFT_OUT.search(p)]


def shorten(sentence: str, start: int) -> tuple[str, int]:
    """At most MAX_LENGTH characters, keeping the matched words in; returns the text and where the match now starts."""
    if len(sentence) <= MAX_LENGTH:
        return sentence, start
    begin = max(0, min(start - 60, len(sentence) - MAX_LENGTH))
    begin = sentence.rfind(" ", 0, begin) + 1 if begin else 0
    end = sentence.rfind(" ", 0, begin + MAX_LENGTH)
    text = ("…" if begin else "") + sentence[begin:end].rstrip(",;: ") + "…"
    return text, start - begin + (1 if begin else 0)


def remedy(herb: str, sentence: str, match: re.Match) -> dict:
    end = match.end()
    while end < len(sentence) and sentence[end].isalpha():  # A stem ("consolidat*") is bolded to the end of its word.
        end += 1
    text, start = shorten(sentence, match.start())
    return {"herb": herb, "text": text, "match": [start, start + end - match.start()]}


def latin_name(name: str, latin: dict[str, str]) -> str | None:
    """The botanical name for a herb, from herb_latin.json: keyed by the start of its name, the longest key wins."""
    keys = [k for k in latin if not k.startswith("_")
            and (name == k or (name.startswith(k) and not name[len(k)].isalnum()))]
    return latin[max(keys, key=len)] if keys else None


def build(book: str, latin: dict[str, str] | None = None) -> dict:
    """Remedies by ailment (for /cure), and each herb with what it treats (for /plant)."""
    latin = latin or {}
    remedies = {a.name: [] for a in AILMENTS}
    allheal, herb_list = [], []
    for herb in herbs(book):
        treats: dict[str, int] = {}
        for sentence in sentences(herb.virtues):
            if herb.name.lower() in ("all-heal", "self-heal", "allheal"):
                allheal.append({"herb": herb.name, "text": shorten(sentence, 0)[0], "match": [0, 0]})
            for ailment in AILMENTS:
                if found := ailment.pattern.search(sentence):
                    remedies[ailment.name].append(remedy(herb.name, sentence, found))
                    treats[ailment.name] = treats.get(ailment.name, 0) + 1
        if not treats and not herb.headed:
            continue  # Just a pointer to the next herb ("I shall therefore only describe the Dwarf-Elder")
        herb_list.append({"name": herb.name, "aliases": herb.aliases, "latin": latin_name(herb.name, latin),
                          "planet": herb.planet, "treats": sorted(treats, key=lambda a: -treats[a])})
    return {"remedies": remedies, "allheal": allheal, "herbs": herb_list}


def main() -> None:
    print(f"Downloading {SOURCE_URL} ...")
    with urllib.request.urlopen(SOURCE_URL, timeout=60) as response:
        book = response.read().decode("utf-8")
    data = build(book, json.loads(LATIN.read_text(encoding="utf-8")))
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    counts = {name: len(found) for name, found in data["remedies"].items()}
    empty = [name for name, count in counts.items() if not count]
    print(f"{sum(counts.values())} remedies for {len(counts)} ailments, {len(data['allheal'])} for All-heal.")
    herb_list = data["herbs"]
    print(f"{len(herb_list)} herbs, {sum(1 for h in herb_list if h['latin'])} with a Latin name.")
    if empty:
        print("No remedies found for:", ", ".join(empty))
        sys.exit(1)


if __name__ == "__main__":
    main()
