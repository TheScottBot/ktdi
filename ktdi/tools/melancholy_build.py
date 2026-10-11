"""Build /melancholy's passages from Robert Burton's The Anatomy of Melancholy (1621), from Project Gutenberg:
python -m ktdi.tools.melancholy_build

Burton writes in enormous paragraphs, thick with Latin and footnote marks, so whole paragraphs won't do: the
passages are excerpts of a few sentences, picked by hand from each subsection ("Bad Air, a cause of Melancholy"),
and listed word for word in ktdi/lib/melancholy_curation.json with the subsection they're in. The build checks every
one is in the book exactly as listed (footnote marks aside), so nothing is invented or "improved", and writes them
with their subsection's title to ktdi/lib/melancholy.json. The book is public domain; it's downloaded each time
(about 3 MB).

To add a passage, copy a few sentences from the book (without the footnote marks) into "keep", under its
subsection's title.
"""

import json
import re
import unicodedata

from ktdi.lib import links
from ktdi.tools import gutenberg

BOOK = 10800
CURATION = gutenberg.curation_file("melancholy")
START = "\nDEMOCRITUS JUNIOR TO THE READER.\n"
STOP = "\nNotes\n"
FOOTNOTE = re.compile(r"\[\d+\]\s?")  # "[1505]If it be impure"
# Where a part starts, and its title: "SUBSECT. V.—_Bad Air, a cause of Melancholy_.", or a heading line followed
# by its title in italics on the next ("THE FIRST SECTION, MEMBER, SUBSECTION." / "_The Preface_.")
HEADING = re.compile(r"^(?:SUBSECT\. [IVXL]+\.—_(?P<inline>[^_]+(?:\n[^_\n]+)*)_\.?|(?P<line>(?:THE [A-Z ,]+|"
                     r"(?:SECT|MEMB)\. [IVXL]+\.(?: MEMB\. [IVXL]+\.)?(?: SUBSECT\. [IVXL]+\.)?)\.?)\n\n"
                     r"_(?P<next>[^_]+(?:\n[^_\n]+)*)_\.?)$", re.M)


ESCAPED = re.compile(r"\\u([0-9a-fA-F]{4})")  # One copy of the book writes its Greek as "Φ..."; the other doesn't


def unescape(text: str) -> str:
    """Greek as Greek, however the copy wrote it: escaped ("\\u03a6"), or with accents encoded either of the ways
    Unicode allows (the mirror's "ί" is gutenberg.org's "ί", NFC-normalised)."""
    return unicodedata.normalize("NFC", ESCAPED.sub(lambda m: chr(int(m.group(1), 16)), text))


def tidy(text: str) -> str:
    """Footnote marks out, one line, one space between words, Greek as Greek."""
    return " ".join(unescape(FOOTNOTE.sub("", text)).split())


def subsections(book: str) -> list[dict]:
    """The book's parts, in order: {"title": "Bad Air, a cause of Melancholy", "text": "...", "marked": "..."},
    starting with Burton's preface, "Democritus Junior to the Reader". "text" has the footnote marks taken out;
    "marked" keeps them (on one line), as the book's web page shows them ("of whom [63] Felix Plater speaks")."""
    book = book.replace("\r\n", "\n")
    body = book[book.index(START):book.index(STOP)]
    marks = list(HEADING.finditer(body))
    spans = [("Democritus Junior to the Reader", body[:marks[0].start()] if marks else body)]
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        title = unescape(" ".join((mark.group("inline") or mark.group("next")).split())).rstrip(".")
        spans.append((title, body[mark.end():end]))
    parts = [{"title": title, "text": tidy(text), "marked": " ".join(unescape(text).split())} for title, text in spans]
    return [part for part in parts if part["text"]]


def anchor(excerpt: str, marked: str) -> str:
    """The words for a link to find the excerpt by on the book's web page, where the footnote marks are still in the
    text: the excerpt's first (or longest) run of plain words with no footnote mark among them."""
    words = [re.escape(word) for word in excerpt.split()]
    found = re.search(r"(?:\[\d+\]\s?)?" + r"\s+(?:\[\d+\]\s?)?".join(words), marked)
    return links.fragment_text(found.group(0) if found else excerpt)


def build(book: str, curation: dict) -> dict:
    """The passages on the allowlist, each with its subsection's title, checked against the book word for word."""
    parts = {part["title"]: part for part in subsections(book)}
    passages, missing = [], []
    for title, excerpts in curation["keep"].items():
        title = unescape(title)
        for excerpt in excerpts:
            excerpt = unescape(" ".join(excerpt.split()))
            if title in parts and excerpt in parts[title]["text"]:
                passages.append({"title": title, "text": excerpt, "anchor": anchor(excerpt, parts[title]["marked"])})
            else:
                missing.append(f"{title}: {excerpt[:60]}")
    return {"passages": passages, "missing": missing}


def main() -> None:
    book = gutenberg.download(BOOK)
    curation = json.loads(CURATION.read_text(encoding="utf-8"))
    data = build(book, curation)
    missing = data.pop("missing")
    (gutenberg.LIB / "melancholy.json").write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(data['passages'])} passages from {len(curation['keep'])} subsections.")
    if missing:  # Not in the book as written: a typo in the curation, or the book's been re-transcribed
        raise SystemExit("Not found in the book:\n  " + "\n  ".join(missing))


if __name__ == "__main__":
    main()
