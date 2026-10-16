"""Shared by the tools that build a command's data from a Project Gutenberg book (slang_build, devils_build,
dream_build): downloading the book, and building from a hand-read allowlist.

Allowlist builds: a book's entries were reviewed once, entry by entry, and only the headwords kept are recorded (in
ktdi/lib/<name>_curation.json, as {"keep": [...]}), so nothing taken out (slurs and the like) is ever in the repo.
"""

import html
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

LIB = Path(__file__).resolve().parent.parent / "lib"
END = "*** END OF THE PROJECT GUTENBERG"
SMALL_WORDS = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "of", "on", "or", "the", "to", "with"}
ROMAN = re.compile(r"^((?=[IVXLC])C{0,3}(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3}))(\.?(?:'S)?,?)$")  # Not "CIVIL"
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


def titled(title: str) -> str:
    """A title in capitals as a title: "FOX KILLED BY A SWAN." is "Fox Killed by a Swan"; "HENRY VIII.'S WALKING
    STICK" keeps its numerals."""
    words = []
    for i, word in enumerate(title.rstrip(".").split()):
        numeral = ROMAN.match(word)
        if numeral and word not in ("I", "A"):
            words.append(numeral[1] + numeral[2].lower())  # "VIII.'S" is "VIII.'s"
        elif i and word.lower() in SMALL_WORDS:
            words.append(word.lower())
        else:  # "SO-CALLED" is "So-Called", "JOHNSON'S" is "Johnson's"
            words.append(re.sub(r"[^\W_]+(?:'[^\W_]+)?", lambda m: m[0][:1].upper() + m[0][1:], word.lower()))
    return " ".join(words)


def html_text(fragment: str) -> str:
    """A bit of a book's web page as text (for a book whose pictures are wanted: /wonder, /goblin): italics as
    _italics_ (as Gutenberg's plain text has them, so oldbooks.escape shows them), raised letters in their word
    ("y<sup>e</sup>" is "ye"), paragraphs apart, lines of verse and table rows on lines of their own, and page
    numbers, pictures' captions, footnote marks and the footnotes themselves out."""
    fragment = " ".join(fragment.split())  # The page's own line breaks mean nothing
    fragment = re.sub(r'<div class="footnotes">.*', "", fragment)  # A section's footnotes are at its end
    fragment = re.sub(r'<span class="pagenum"[^>]*>.*?</span>|<a [^>]*class="fnanchor[^"]*"[^>]*>.*?</a>', "", fragment)
    fragment = re.sub(r'<div class="caption[^"]*">.*?</div>|<p class="caption[^"]*">.*?</p>', "", fragment)
    fragment = re.sub(r"<(i|em)\b[^>]*>(.*?)</\1>", lambda m: f"_{m[2].strip()}_" if m[2].strip() else m[2], fragment)
    fragment = re.sub(r'</p>|</table>|<div class="(?:poem|stanza)[^"]*">', "\n\n", fragment)
    fragment = re.sub(r"<br\s*/?>|</tr>|</div>", "\n", fragment)
    fragment = re.sub(r"</t[dh]>\s*<t[dh][^>]*>", " — ", fragment)
    fragment = html.unescape(re.sub(r"<[^>]+>", "", fragment)).replace("\xa0", " ")
    paragraphs = ["\n".join(" ".join(line.split()) for line in block.split("\n") if line.strip())
                  for block in re.split(r"\n\s*\n", fragment)]
    return "\n\n".join(p for p in paragraphs if p)


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


HEADING = re.compile(r"<h([234])\b[^>]*>(.*?)</h\1>", re.S)


def headed_paragraphs(body: str) -> list[dict]:
    """A book of chapters (<h2>) in sections (<h3> or <h4>) as its paragraphs, in order (for /omen and /gemlore,
    whose sections run to pages): {"key": "3.5.2", "chapter": 3, "chapter_title", "section": 5, "section_title",
    "paragraph": 2, "text"}. Sections are counted from 1 in each chapter; what's before a chapter's first section
    (its motto, its introduction) is section 0. Titles are as the page has them."""
    heads = list(HEADING.finditer(body))
    found, chapter, chapter_title, section, section_title = [], 0, "", 0, ""
    for i, head in enumerate(heads):
        content = body[head.end():heads[i + 1].start() if i + 1 < len(heads) else len(body)]
        title = " ".join(html_text(head[2]).split())
        if head[1] == "2":
            chapter, chapter_title, section, section_title = chapter + 1, title, 0, ""
        else:
            section, section_title = section + 1, title
        for n, text in enumerate((p for p in html_text(content).split("\n\n") if p), start=1):
            found.append({"key": f"{chapter}.{section}.{n}", "chapter": chapter, "chapter_title": chapter_title,
                          "section": section, "section_title": section_title, "paragraph": n, "text": text})
    return found


def mid_sentence(paragraph: str, following: str) -> bool:
    """Whether the book broke a sentence across two paragraphs ("...attached much importance to the" | "Eye Amulet,
    which..."): both are prose (not verse, a table or a list, which have lines), and the first ends on a small word
    ("the", "of", "and") or the next goes on in small letters. Not a missing full stop: "...the gem of winter" | "For
    spring"."""
    last = paragraph.rsplit(" ", 1)[-1]
    return ("\n" not in paragraph + following and last.isalpha() and last.islower()
            and (last in SMALL_WORDS or following[:1].islower()))


def titled_keep(found: dict[str, dict], curation: dict, leave_out: tuple[str, ...] = ()) -> tuple[list[dict], list[str]]:
    """For a book whose parts have numbers but no titles (/goblin's sections, /omen's and /gemlore's paragraphs), so
    the curation gives each one kept a title and other names: {"keep": {"1.2.4": {"title": ..., "also": [...]}}}, and
    for a run of paragraphs, the last one's number ("to": 6 is 1.2.4 to 1.2.6). The parts kept (from `found`, keyed
    and in book order), each with its "title" and "also" and without the fields in `leave_out`; and the keys listed
    that aren't in the book (or whose run isn't)."""
    keep = curation["keep"]
    kept = [{**{k: v for k, v in part.items() if k not in leave_out}, "title": keep[key]["title"],
             "also": keep[key].get("also", [])}
            for key, part in found.items() if key in keep]
    missing = sorted(set(keep) - set(found))
    for part in kept:  # A run: an omen, then its explanation
        last = keep[part["key"]].get("to")
        if last:
            within, first = part["key"].rsplit(".", 1)
            run = [found.get(f"{within}.{n}") for n in range(int(first), last + 1)]
            if None in run:
                missing.append(f"{part['key']} to {last}")
            texts = [p["text"] for p in run if p]
            part["text"] = "".join(t + ("" if i == len(texts) - 1 else " " if mid_sentence(t, texts[i + 1])
                                        else "\n\n") for i, t in enumerate(texts))
    return kept, missing


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
