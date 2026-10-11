"""Shared by the tools that build a command's data from a Project Gutenberg book (slang_build, devils_build,
dream_build): downloading the book, and building from a hand-read allowlist.

Allowlist builds: a book's entries were reviewed once, entry by entry, and only the headwords kept are recorded (in
ktdi/lib/<name>_curation.json, as {"keep": [...]}), so nothing taken out (slurs and the like) is ever in the repo.
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

LIB = Path(__file__).resolve().parent.parent / "lib"
END = "*** END OF THE PROJECT GUTENBERG"
# Where a book's plain text is. gutenberg.org is first; its main mirror is there for when it's down (503s happen).
SOURCES = [
    "https://www.gutenberg.org/cache/epub/{book}/pg{book}.txt",
    "https://gutenberg.pglaf.org/{path}/{book}/{book}-0.txt",
    "https://gutenberg.pglaf.org/{path}/{book}/{book}.txt",
]


def source_urls(book: int) -> list[str]:
    """Where to look for a book, in order. The mirror files it by its digits: book 926 is in 9/2/926/."""
    path = "/".join(str(book)[:-1]) if book >= 10 else "0"
    return [url.format(book=book, path=path) for url in SOURCES]


def download(book: int, timeout: int = 60) -> str:
    """A Gutenberg book's plain text, from gutenberg.org or, if that's down, its mirror."""
    problems = []
    for url in source_urls(book):
        print(f"Downloading {url} ...")
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                return response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as error:
            problems.append(f"{url}: {error}")
    raise SystemExit("Couldn't download the book:\n  " + "\n  ".join(problems))


def curation_file(name: str) -> Path:
    return LIB / f"{name}_curation.json"


def kept(entries: list[dict], keep: list[str]) -> list[dict]:
    """The entries whose headword is on the allowlist, in book order."""
    wanted = set(keep)
    return [entry for entry in entries if entry["word"] in wanted]


def build_from_allowlist(book: int, name: str, entries: Callable[[str], list[dict]],
                         build: Callable[[str, dict], dict] | None = None,
                         headword: Callable[[str], str] = lambda key: key, report: Callable[[dict], str] = lambda d: ""):
    """The whole of an allowlist build tool: download the book, keep what lib/<name>_curation.json lists (or whatever
    `build` makes of it), write lib/<name>.json, and stop with an error if anything listed wasn't found (the book's
    been re-transcribed and a headword's changed). `headword` gets the headword from a "keep" key; `report` adds to
    the summary."""
    text = download(book)
    curation = json.loads(curation_file(name).read_text(encoding="utf-8"))
    data = build(text, curation) if build else {"entries": kept(entries(text), curation["keep"])}
    (LIB / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(data['entries'])} entries kept of {len(entries(text))}.{report(data)}")
    found = {entry["word"] for entry in data["entries"]}
    missing = [key for key in curation["keep"] if headword(key) not in found]
    if missing:
        print("In the curation but not found in the book:", ", ".join(missing))
        sys.exit(1)
