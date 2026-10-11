"""Build /devils's entries from Ambrose Bierce's The Devil's Dictionary (1911), from Project Gutenberg:
python -m ktdi.tools.devils_build

Parses every entry ("BORE, n. A person who talks when you wish him to listen.") with its verse and asides, and keeps
only the ones in ktdi/lib/devils_curation.json. Bierce is cruel to everyone, which is the point, but some entries are
racist, sexist or mock disability by more than 1911's standards; they were reviewed out once, entry by entry, and
only what was kept is recorded, so nothing taken out is ever in the repo. Writes ktdi/lib/devils.json. The book is
public domain; it's downloaded each time (about 400 KB).

To add an entry, read it in the book first, then add its headword to "keep".
"""

import re

from ktdi.tools import gutenberg

BOOK = 972
CURATION = gutenberg.curation_file("devils")
# How an entry starts, as (headword, part of speech, the rest). Verse is signed with initials ("G.J.", "J. Milton
# Sloluck") that look a lot like headwords, so each pattern is strict.
WORD = r"[A-Z][A-Z'-]*(?: (?:\(or [A-Z]+\)|[A-Z][A-Z'-]*))*"
ENTRY_PATTERNS = [
    # "ABSCOND, v.i. To...", "BABE or BABY, n. A...", "CONFIDANT, CONFIDANTE, n. One...", "IMPOSTOR n. A...",
    # "TZETZE (or TSETSE) FLY, n. An..."
    re.compile(rf"^({WORD}(?:(?:, | or ){WORD})*),? ((?:[a-z]+\.\s?)+)\s*(.*)$"),
    # "CUI BONO?  [Latin]  What good..."
    re.compile(rf"^({WORD}\?)\s+(\[Latin\])\s*(.*)$"),
    # No part of speech: "ABRACADABRA.", "HABEAS CORPUS.  A writ..." (four letters or more, so not initials)
    re.compile(r"^([A-Z][A-Z'-]{3,}(?: [A-Z][A-Z'-]*)*)\.()\s*(.*)$"),
    # Abbreviations: "R.I.P.  A careless abbreviation...", "LL.D.  Letters..." (initials have nothing after them)
    re.compile(r"^((?:[A-Z]{1,2}\.){2,})()\s{2,}(\S.*)$"),
    # The letters, whose entries start with the letter: "T, the twentieth letter...", "I is the first letter..."
    re.compile(r"^(?=([A-Z])(?:,| is | in ))()(.*)$"),
]


def entry_head(line: str) -> re.Match | None:
    """The start of an entry, if the line is one."""
    return next((m for pattern in ENTRY_PATTERNS if (m := pattern.match(line))), None)


def entries(book: str) -> list[dict]:
    """Every entry: {"word": "BORE", "pos": "n.", "head": "BORE, n.", "text": "..."}, where "head" is how the entry
    starts in the book (for links to it). Prose paragraphs are joined up; verse (indented in the book) keeps its lines.
    Paragraphs are separated by a blank line."""
    book = book.replace("\r\n", "\n")
    body = book[:book.index(gutenberg.END)]
    found, paragraphs, lines = [], [], []

    def close_paragraph():
        if lines:
            verse = all(line.startswith(" ") for line in lines)
            paragraphs.append("\n".join(l.strip() for l in lines) if verse else " ".join(l.strip() for l in lines))
            lines.clear()

    def close_entry():
        close_paragraph()
        if found:
            found[-1]["text"] = "\n\n".join(p for p in paragraphs if p)
        paragraphs.clear()

    started = False
    for line in body.split("\n"):
        head = entry_head(line)
        if head:
            close_entry()
            started = True
            found.append({"word": head.group(1), "pos": (head.group(2) or "").strip(),
                          "head": " ".join(line[:head.start(3)].split()), "text": ""})
            lines.append(head.group(3))
        elif started:
            if re.fullmatch(r"[A-Z]", line.strip()):  # A section's letter, before its first entry
                close_paragraph()
            elif line.strip():
                lines.append(line)
            else:
                close_paragraph()
    close_entry()
    return found


def main() -> None:
    gutenberg.build_from_allowlist(BOOK, "devils", entries)


if __name__ == "__main__":
    main()
