"""Build /cure's remedies from Culpeper's Complete Herbal (1653), from Project Gutenberg:  python -m ktdi.tools.cure_build

Reads each herb's "Government and virtues" (what it cures, in Culpeper's words), finds the sentences that mention each
ailment in ktdi/lib/ailments.py, and writes ktdi/lib/cures.json. Run it again after changing an ailment's `culpeper`
terms. The book is public domain; it's downloaded each time (about 1.5 MB).
"""

import json
import re
import sys
import urllib.request
from pathlib import Path

from ktdi.lib.ailments import AILMENTS

SOURCE_URL = "https://www.gutenberg.org/cache/epub/49513/pg49513.txt"
OUTPUT = Path(__file__).resolve().parent.parent / "lib" / "cures.json"
HERB_RE = re.compile(r"^ {2,}([A-Z][A-Z ,'’\-()&.]+?)\.?\s*$", re.MULTILINE)
VIRTUES_RE = re.compile(r"_Government and virtues\._\]\s*(.*?)(?=\n\s*\n_[A-Z][a-z]|\Z)", re.IGNORECASE | re.DOTALL)
MAX_LENGTH = 350
# A few of the herbal's remedies are for ending pregnancies or delivering stillbirths. Not for a joke command.
LEFT_OUT = re.compile(r"abort|dead child|miscarr|bring away the birth|kill the child|untimely birth", re.IGNORECASE)


def herb_name(header: str) -> str:
    name = " ".join(header.split()).title().replace("’", "'")
    return re.sub(r"\b(Or|Of|The|And|In|With)\b", lambda m: m.group(1).lower(), name).replace("'S", "'s")


def herbs(text: str) -> list[tuple[str, str]]:
    """(herb, its Government and virtues text) for each herb in the book."""
    text = text.replace("\r\n", "\n")
    headers = list(HERB_RE.finditer(text))
    found = []
    for header, following in zip(headers, headers[1:] + [None]):
        block = text[header.end():following.start() if following else len(text)]
        virtues = VIRTUES_RE.search(block)
        if virtues:  # Gutenberg marks italics _like this_; Discord would show the underscores.
            found.append((herb_name(header.group(1)), " ".join(virtues.group(1).replace("_", "").split())))
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


def build(book: str) -> dict:
    remedies = {a.name: [] for a in AILMENTS}
    allheal = []
    for herb, virtues in herbs(book):
        for sentence in sentences(virtues):
            if herb.lower() in ("all-heal", "self-heal", "allheal"):
                allheal.append({"herb": herb, "text": shorten(sentence, 0)[0], "match": [0, 0]})
            for ailment in AILMENTS:
                if found := ailment.pattern.search(sentence):
                    remedies[ailment.name].append(remedy(herb, sentence, found))
    return {"remedies": remedies, "allheal": allheal}


def main() -> None:
    print(f"Downloading {SOURCE_URL} ...")
    with urllib.request.urlopen(SOURCE_URL, timeout=60) as response:
        book = response.read().decode("utf-8")
    data = build(book)
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    counts = {name: len(found) for name, found in data["remedies"].items()}
    empty = [name for name, count in counts.items() if not count]
    print(f"{sum(counts.values())} remedies for {len(counts)} ailments, {len(data['allheal'])} for All-heal.")
    if empty:
        print("No remedies found for:", ", ".join(empty))
        sys.exit(1)


if __name__ == "__main__":
    main()
