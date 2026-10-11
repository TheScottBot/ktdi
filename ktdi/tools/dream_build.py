"""Build /dream's entries from Gustavus Hindman Miller's Ten Thousand Dreams Interpreted (1901), from Project Gutenberg:
python -m ktdi.tools.dream_build

Parses every entry ("_Eel_." and what dreaming of one foretells) and keeps only the ones in
ktdi/lib/dream_curation.json. Miller's 1901 is very 1901: entries that are racist, cruel about disability, or about
sex, violence against women or the like were reviewed out once, entry by entry, and only what was kept is recorded,
so nothing taken out is ever in the repo. "For a young woman to dream..." stays: that's the joke. Writes
ktdi/lib/dream.json. The book is public domain; it's downloaded each time (about 900 KB).

To add an entry, read it in the book first, then add its headword to "keep".
"""

import re

from ktdi.tools import gutenberg

BOOK = 926
START = "WHAT'S IN A DREAM."  # The dictionary, after Miller's preface
STOP = "\nINDEX\n"
HEADING = re.compile(r"^_([^_]+?)_\.?(?:\[\d+\])*\s*$")  # "_Eel_.", "_Abbey_.[3]"
# A few headings share a line: "_Canary Birds_.  To dream...", "...in a fair way to success.  _Katydids_."
HEAD = r"_[A-Z][^_]{0,40}_\.(?:\[\d+\])*"
STARTS_LINE = re.compile(rf"^({HEAD}) +", re.M)
ENDS_LINE = re.compile(rf"  ({HEAD})$", re.M)
LETTER = re.compile(r"^[A-Z]\.(?:\s|$)")  # A letter's section ("B."), with a Bible verse before its first entry
FOOTNOTE = re.compile(r"^\[\d+\]")  # "[19] See Cask."
QUOTES = [("``", "“"), ("''", "”"), ("`", "‘"), ("{sic}", "")]


def tidy(text: str) -> str:
    """One paragraph, as a line: the scan's TeX-style quotes made real, footnote marks taken out."""
    text = " ".join(text.split())
    for old, new in QUOTES:
        text = text.replace(old, new)
    return re.sub(r"\[\d+\]", "", text).strip()


def entries(book: str) -> list[dict]:
    """Every entry: {"word": "Eel", "text": "To dream of an eel is good...\n\nTo see an eel..."}, paragraphs separated
    by a blank line."""
    book = book.replace("\r\n", "\n")
    body = book[book.index(START):book.index(STOP)]
    body = ENDS_LINE.sub(r"\n\n\1", STARTS_LINE.sub(r"\1\n\n", body))  # Every heading a paragraph of its own
    found, current = [], None
    for paragraph in re.split(r"\n\s*\n", body):
        line = paragraph.strip()
        if heading := HEADING.match(line):
            current = {"word": " ".join(heading.group(1).split()), "paragraphs": []}
            found.append(current)
        elif LETTER.match(line):
            current = None  # Until the next entry: the section's verse isn't part of the last one
        elif current is not None and line and not FOOTNOTE.match(line):
            current["paragraphs"].append(tidy(line))
    # A few entries are only a footnote pointing elsewhere ("_Barrel_.[19]", "[19] See Cask."): those are left out.
    return [{"word": entry["word"], "text": "\n\n".join(p for p in entry["paragraphs"] if p)}
            for entry in found if any(entry["paragraphs"])]


def main() -> None:
    gutenberg.build_from_allowlist(BOOK, "dream", entries)


if __name__ == "__main__":
    main()
