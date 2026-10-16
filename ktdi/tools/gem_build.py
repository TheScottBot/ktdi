"""Build /gemlore's stones from George Frederick Kunz's The Curious Lore of Precious Stones (1913; public domain,
Project Gutenberg 57978): python -m ktdi.tools.gem_build

Kunz, Tiffany's gem expert, gathered what the world had believed about precious stones: talismans and amulets, the
virtues of each stone (agate to turquoise), engraved gems, ominous and luminous stones, crystal balls, the
High-Priest's breastplate, birthstones, and the stones of the planets, the days and the hours. It's a compilation
looking back, and some of what it says the ancients believed is disputed; /gemlore says so.

The chapters run to pages, so what's kept is a paragraph, or a short run of them (one stone and what was believed of
it), filed under its chapter and section. The last chapter, on stones as medicine, isn't kept: it's remedies.

ktdi/lib/gem_curation.json gives each one kept a title of its own, other names to look it up by (its stones first),
and if one of the book's pictures shows it, that picture: {"keep": {"3.1.4": {"title": "Agate Against Thirst",
"also": ["agate"], "to": 5, "picture": "i_020fp"}}}, keyed chapter.section.paragraph (counted from 1; a chapter's
part before its first section is section 0), with "to" for a run. The book was read once, and what's 1913 at its
worst left out. Writes ktdi/lib/gems.json.

To add one, read it in the book, then add its key and a title to "keep".
"""

import json
import re
import sys

from ktdi.tools import gutenberg

BOOK = 57978
CURATION = gutenberg.curation_file("gem")
IMAGES = f"https://www.gutenberg.org/cache/epub/{BOOK}/"
LARGER = re.compile(r'<a href="(images/[^"]+)"[^>]*>here</a>')  # A thumbnail's "A larger image is available here"
DIV = re.compile(r"<div\b|</div>")
CAPTION_AFTER = re.compile(r'\s*(<div class="small">.*?</div>|<ul class="small">.*?</ul>)', re.S)


def chapters(page: str) -> str:
    """Chapters I to X: the book without its front matter, its chapter on remedies (XI), its index and footnotes."""
    return page[page.index('<h2><a id="I">'):page.index('<h2><a id="XI">')]


def figures(body: str) -> list[tuple[int, int, str, str]]:
    """Where the pictures are, as (start, end, image, caption's markup). A picture is a <div class="figcenter"> with
    its image and usually its caption inside; one without has it just after, in a <div class="small"> or a list."""
    found = []
    for start in (m.start() for m in re.finditer(r'<div class="figcenter"', body)):
        depth, end = 0, start
        for tag in DIV.finditer(body, start):
            depth += 1 if tag[0] == "<div" else -1
            if not depth:
                end = tag.end()
                break
        figure = body[start:end]
        # Unwrapped, as gutenberg.html_text leaves captions out
        caption = re.sub(r'<img [^>]*>|<a id=[^>]*></a>|<div class="caption[^"]*"[^>]*>', "", figure)
        if not gutenberg.html_text(caption):
            after = CAPTION_AFTER.match(body, end)
            if after:
                caption, end = after[1], after.end()
        found.append((start, end, re.search(r'<img [^>]*src="([^"]+)"', figure)[1], caption))
    return found


def without_pictures(body: str) -> str:
    for start, end, *_ in reversed(figures(body)):
        body = body[:start] + body[end:]
    return body


def pictures(page: str) -> dict[str, dict]:
    """The book's pictures by name ("i_020fp"): {"url", "caption"}, the larger image where there's a thumbnail."""
    found = {}
    for _, _, src, caption in figures(chapters(page)):
        larger = LARGER.search(caption)
        caption = re.sub(r'<p class="limage">.*?</p>', "", caption, flags=re.S)
        text = gutenberg.html_text(caption.replace("</li>", "<br>")).replace("\n\n", "\n")
        text = re.sub(r"\s*\(See p(?:age)?\. \d+\.?\)|\s*See page \d+\.|^\d+t\s+", "", text)  # Page references; "332t", a stray label
        lines = text.split("\n")
        if lines[0].isupper():
            lines[0] = gutenberg.titled(lines[0])
        found[re.sub(r"thumb$", "", src.rsplit("/", 1)[1].rsplit(".", 1)[0])] = {
            "url": IMAGES + (larger[1] if larger else src), "caption": "\n".join(lines)}
    return found


def opening(text: str) -> str:
    """A chapter's first word, in capitals in the book ("FROM the earliest times"), as a word: "From the..."."""
    return re.sub(r"^([A-Z])([A-Z’']+)\b(?=\s+[a-z])", lambda m: m[1] + m[2].lower(), text)


def chapter_name(title: str) -> str:
    """"I Superstitions and Their Sources" is "Superstitions and Their Sources"; "VII" alone is ""."""
    number, _, name = title.partition(" ")
    return name if gutenberg.ROMAN.match(number) else title


def paragraphs(page: str) -> list[dict]:
    """Every paragraph of chapters I to X, in book order, pictures out: {"key": "3.1.2", "chapter": 3, "section": 1,
    "paragraph": 2, "where": "On the Talismanic Use of Special Stones: Agate", "text"}."""
    found = []
    for p in gutenberg.headed_paragraphs(without_pictures(chapters(page))):
        name = chapter_name(p["chapter_title"])
        section = p["section_title"].rstrip(".")
        section = gutenberg.titled(section) if section.isupper() else section
        if not name:  # Chapter VII's title is its one section's
            name, section = section, ""
        found.append({"key": p["key"], "chapter": p["chapter"], "section": p["section"], "paragraph": p["paragraph"],
                      "where": f"{name}: {section}" if section else name, "text": opening(p["text"])})
    return found


def build(page: str, curation: dict) -> dict:
    """The paragraphs on the allowlist, in book order, each with its title, other names and picture; and any listed
    that aren't in the book (or whose picture isn't)."""
    gems, missing = gutenberg.titled_keep({p["key"]: p for p in paragraphs(page)}, curation,
                                          leave_out=("chapter", "section", "paragraph"))
    found = pictures(page)
    for gem in gems:
        name = curation["keep"][gem["key"]].get("picture")
        gem["picture"] = found.get(name) if name else None
        if name and name not in found:
            missing.append(f"{gem['key']}'s picture {name}")
    return {"gems": gems, "missing": missing}


def main() -> None:
    page = gutenberg.download(BOOK, html=True)
    curation = json.loads(CURATION.read_text(encoding="utf-8"))
    data = build(page, curation)
    missing = data.pop("missing")
    (gutenberg.LIB / "gems.json").write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(data['gems'])} passages kept of {len(paragraphs(page))} paragraphs, "
          f"{sum(bool(g['picture']) for g in data['gems'])} with a picture.")
    if missing:
        print("In the curation but not found in the book:", ", ".join(missing))
        sys.exit(1)


if __name__ == "__main__":
    main()
