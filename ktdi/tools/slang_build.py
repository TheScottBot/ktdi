"""Build /vulgartongue's dictionary from Grose's 1811 Dictionary of the Vulgar Tongue, from Project Gutenberg:
python -m ktdi.tools.slang_build

Parses every entry and keeps only the ones in ktdi/lib/slang_curation.json, which also picks the insults for
/vulgartongue insult. The book has slurs, and plenty that's sexist, racist, xenophobic, homophobic or transphobic,
about sex, or mocking disability; it was reviewed once (by word list, then entry by entry) and only what was kept is
recorded, so nothing taken out is ever in the repo. Writes ktdi/lib/slang.json. The book is public domain; it's
downloaded each time (about 500 KB).

To add an entry, read it in the book first, then add its headword to "keep" (and "insults", if it is one).
"""

import re

from ktdi.tools import gutenberg

BOOK = 5402
CURATION = gutenberg.curation_file("slang")
START = "DICTIONARY OF THE VULGAR TONGUE.\n\n\n"  # The dictionary proper, after the prefaces.
WORD = r"[A-Z][A-Z0-9'’\-&]*(?: [A-Z0-9'’\-&()]+)*"
HEAD_RE = re.compile(rf"^((?:To |TO |A |AN )?{WORD}(?:,? (?:or|OR) (?:TO |To )?{WORD})*)\s*[.,;:]\s+(.+)$", re.S)


def entries(book: str) -> list[dict]:
    """Every entry: {"word": "ADDLE PATE", "text": "An inconsiderate foolish fellow."}. Lines that don't start an
    entry (verses, lists) belong to the one before."""
    book = book.replace("\r\n", "\n")
    body = book[book.index(START):gutenberg.end_of(book)].split("\n", 1)[1]
    found = []
    for paragraph in re.split(r"\n\s*\n", body):
        paragraph = " ".join(paragraph.split())
        if not paragraph:
            continue
        head = HEAD_RE.match(paragraph)
        if head and sum(c.isupper() for c in head.group(1)) >= 2:
            found.append({"word": head.group(1).strip(), "text": head.group(2).strip()})
        elif found:
            found[-1]["text"] += " " + paragraph
    return found


def picked(entry: dict, keys: list[str]) -> bool:
    """Whether the curation names this entry: by headword ("JACOB"), or, where a headword's used for more than one
    entry, by headword and how its definition starts ("JACOB :: A soft fellow")."""
    full = f"{entry['word']} :: {entry['text']}"
    return any(full.startswith(key) if " :: " in key else entry["word"] == key for key in keys)


def build(book: str, curation: dict) -> dict:
    kept = [e for e in entries(book) if picked(e, curation["keep"])]
    for entry in kept:
        entry["insult"] = picked(entry, curation["insults"])
    return {"entries": kept}


def main() -> None:
    gutenberg.build_from_allowlist(BOOK, "slang", entries, build=build, headword=lambda key: key.split(" :: ")[0],
                                   report=lambda data: f" {sum(e['insult'] for e in data['entries'])} are insults.")


if __name__ == "__main__":
    main()
