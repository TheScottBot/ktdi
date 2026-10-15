"""Shared by the tools that build a command's data from a Project Gutenberg book (slang_build, devils_build,
dream_build): downloading the book, and building from a hand-read allowlist.

Allowlist builds: a book's entries were reviewed once, entry by entry, and only the headwords kept are recorded (in
ktdi/lib/<name>_curation.json, as {"keep": [...]}), so nothing taken out (slurs and the like) is ever in the repo.
"""

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

LIB = Path(__file__).resolve().parent.parent / "lib"
END = "*** END OF THE PROJECT GUTENBERG"
OLD_END = "*** END OF THIS PROJECT GUTENBERG"  # How older ebooks (and some of the mirror's copies) end


def end_of(book: str) -> int:
    """Where the book itself ends and Project Gutenberg's licence begins, however this copy marks it."""
    return next(book.index(marker) for marker in (END, OLD_END) if marker in book)


# Where a book's plain text is. gutenberg.org is first; its main mirror is there for when it's down (503s happen).
SOURCES = [
    "https://www.gutenberg.org/cache/epub/{book}/pg{book}.txt",
    "https://gutenberg.pglaf.org/{path}/{book}/{book}-0.txt",
    "https://gutenberg.pglaf.org/{path}/{book}/{book}.txt",
]
HTML_SOURCES = [  # The web page, for a book whose pictures are wanted (/wonder)
    "https://www.gutenberg.org/cache/epub/{book}/pg{book}-images.html",
    "https://gutenberg.pglaf.org/{path}/{book}/{book}-h/{book}-h.htm",
]


def source_urls(book: int, html: bool = False) -> list[str]:
    """Where to look for a book, in order. The mirror files it by its digits: book 926 is in 9/2/926/."""
    path = "/".join(str(book)[:-1]) if book >= 10 else "0"
    return [url.format(book=book, path=path) for url in (HTML_SOURCES if html else SOURCES)]


def download(book: int, timeout: int = 60, html: bool = False) -> str:
    """A Gutenberg book's plain text (or with html, its web page), from gutenberg.org or, if that's down, its
    mirror."""
    problems = []
    for url in source_urls(book, html):
        print(f"Downloading {url} ...")
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                return response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as error:
            problems.append(f"{url}: {error}")
    raise SystemExit("Couldn't download the book:\n  " + "\n  ".join(problems))


# A paragraph starting with its number: "110. INGREDIENTS.--...", "1000. Lighting Candles." (not "stock No.\n105.")
NUMBERED = re.compile(r"(?:\A|\n[ \t]*\n)(\d+)\.\s+")
CAPITALS = re.compile(r"^[^a-z]*[A-Z][^a-z]*$")
ILLUSTRATION = re.compile(r"^\[Illustration.*\]$")


def is_heading(line: str) -> bool:
    """A line in capitals ("ALMOND SOUP.", "II.", "CUCUMBER SOUP (French Recipe).", brackets and "&c." aside), one
    that starts in capitals and goes on in small letters ("YORKSHIRE PUDDING, to serve with hot Roast Beef."), or a
    subtitle in brackets on its own ("(_Economical_.)", "_(More Economical.)_")."""
    line = line.replace("_", "")
    return bool(re.fullmatch(r"\(.*\)\.?", line) or CAPITALS.match(re.sub(r"\([^)]*\)|&c", "", line))
                or (len(line) < 80 and re.match(r"[A-Z][A-Z'’ -]{3,}, [a-z]", line)))


def numbered_sections(text: str) -> list[dict]:
    """A book of numbered paragraphs (Beeton, Enquire Within) as {"number": 110, "headings": [...], "text": ...}.
    A section runs to the next number. Lines in capitals just before a number ("ALMOND SOUP.", "I.") are that
    section's headings, not the end of the one before; the text is the section's own lines, number taken off."""
    def split_headings(lines: list[str]) -> list[str]:
        """Take the lines in capitals off the end (they head the next section)."""
        headings = []
        while lines and (not lines[-1].strip() or is_heading(lines[-1].strip())
                         or ILLUSTRATION.match(lines[-1].strip())):
            line = lines.pop().strip()
            if line and not ILLUSTRATION.match(line):  # Pictures between a title and its number aren't headings
                headings.insert(0, line)
        return headings

    starts = list(NUMBERED.finditer(text))
    headings = split_headings(text[:starts[0].start()].rstrip().split("\n")) if starts else []
    sections = []
    for i, match in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        lines = text[match.end():end].rstrip().split("\n")
        next_headings = split_headings(lines)
        sections.append({"number": int(match.group(1)), "headings": headings, "text": "\n".join(lines).strip()})
        headings = next_headings
    return sections


def curation_file(name: str) -> Path:
    return LIB / f"{name}_curation.json"


def kept(entries: list[dict], keep: list, key: Callable[[dict], object] = lambda entry: entry["word"]) -> list[dict]:
    """The entries on the allowlist (by headword, or whatever `key` says identifies one), in book order."""
    wanted = set(keep)
    return [entry for entry in entries if key(entry) in wanted]


def build_from_allowlist(book: int, name: str, entries: Callable[[str], list[dict]],
                         build: Callable[[str, dict], dict] | None = None,
                         headword: Callable[[str], object] = lambda key: key, report: Callable[[dict], str] = lambda d: "",
                         key: Callable[[dict], object] = lambda entry: entry["word"]):
    """The whole of an allowlist build tool: download the book, keep what lib/<name>_curation.json lists (or whatever
    `build` makes of it), write lib/<name>.json, and stop with an error if anything listed wasn't found (the book's
    been re-transcribed and a headword's changed). `key` is what identifies an entry on the allowlist (its headword,
    or its paragraph number); `headword` gets that from a "keep" item; `report` adds to the summary."""
    text = download(book)
    curation = json.loads(curation_file(name).read_text(encoding="utf-8"))
    data = build(text, curation) if build else {"entries": kept(entries(text), curation["keep"], key)}
    (LIB / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(data['entries'])} entries kept of {len(entries(text))}.{report(data)}")
    found = {key(entry) for entry in data["entries"]}
    missing = [str(item) for item in curation["keep"] if headword(item) not in found]
    if missing:
        print("In the curation but not found in the book:", ", ".join(missing))
        sys.exit(1)
