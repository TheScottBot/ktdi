"""Build /vulgartongue's dictionary from Grose's 1811 Dictionary of the Vulgar Tongue, from Project Gutenberg:
python -m ktdi.tools.slang_build

Parses every entry and keeps only the ones in ktdi/lib/slang_curation.json, which also picks the insults for
/vulgartongue insult. The book has slurs, and plenty that's sexist, racist, xenophobic, homophobic or transphobic,
about sex, or mocking disability; it was reviewed once (by word list, then entry by entry) and only what was kept is
recorded, so nothing taken out is ever in the repo. Writes ktdi/lib/slang.json. The book is public domain; it's
downloaded each time (about 500 KB).

To add an entry, read it in the book first, then add its headword to "keep" (and "insults", if it is one).
"""

import json
import re
import sys
import urllib.request
from pathlib import Path

SOURCE_URL = "https://www.gutenberg.org/cache/epub/5402/pg5402.txt"
LIB = Path(__file__).resolve().parent.parent / "lib"
OUTPUT = LIB / "slang.json"
CURATION = LIB / "slang_curation.json"
START = "DICTIONARY OF THE VULGAR TONGUE.\n\n\n"  # The dictionary proper, after the prefaces.
END = "*** END OF THE PROJECT GUTENBERG"
WORD = r"[A-Z][A-Z0-9'’\-&]*(?: [A-Z0-9'’\-&()]+)*"
HEAD_RE = re.compile(rf"^((?:To |TO |A |AN )?{WORD}(?:,? (?:or|OR) (?:TO |To )?{WORD})*)\s*[.,;:]\s+(.+)$", re.S)


def entries(book: str) -> list[dict]:
    """Every entry: {"word": "ADDLE PATE", "text": "An inconsiderate foolish fellow."}. Lines that don't start an
    entry (verses, lists) belong to the one before."""
    book = book.replace("\r\n", "\n")
    body = book[book.index(START):book.index(END)].split("\n", 1)[1]
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
    print(f"Downloading {SOURCE_URL} ...")
    with urllib.request.urlopen(SOURCE_URL, timeout=60) as response:
        book = response.read().decode("utf-8")
    curation = json.loads(CURATION.read_text(encoding="utf-8"))
    data = build(book, curation)
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    kept = data["entries"]
    print(f"{len(kept)} entries kept of {len(entries(book))}, {sum(e['insult'] for e in kept)} of them insults.")
    found = {e["word"] for e in kept}
    missing = [key for key in curation["keep"] if key.split(" :: ")[0] not in found]
    if missing:  # The book's been re-transcribed and a headword's changed.
        print("In the curation but not found in the book:", ", ".join(missing))
        sys.exit(1)


if __name__ == "__main__":
    main()
