"""Build /goblin's tales from Wirt Sikes's British Goblins: Welsh Folk-lore, Fairy Mythology, Legends and Traditions
(1880; public domain, Project Gutenberg 34704): python -m ktdi.tools.goblin_build

Sikes, the American consul in Cardiff, collected the fairies, ghosts, spectral hounds, corpse candles, lake maidens
and old customs of Wales, as people told them to him. The book is in four books of chapters, and each chapter in
short numbered sections, each about one creature, place or incident, which is what's kept. It's read from the book's
web page, as that's where T. H. Thomas's illustrations are (each stays with its section).

The sections have numbers but no titles, so ktdi/lib/goblin_curation.json gives each one kept a title (from its
chapter's own list of topics where it can: "Rowli Pugh and the Ellyll"), and other names to look it up by:
{"keep": {"1.2.4": {"title": ..., "also": [...]}}}, keyed book.chapter.section. The book was read once, and its
dull stretches and what's 1880 at its worst left out. Writes ktdi/lib/goblin.json.

To add one, read it in the book, then add its key and a title to "keep".
"""

import html
import json
import re
import sys

from ktdi.lib import roman
from ktdi.tools import gutenberg

BOOK = 34704
IMAGES = f"https://www.gutenberg.org/cache/epub/{BOOK}/"
CURATION = gutenberg.curation_file("goblin")
HEADING = re.compile(r"<h([234])\b[^>]*>(.*?)</h\1>", re.S)
NOT_PICTURES = re.compile(r"images/(?:bgm\d+|bg13|bg15|bg21)\.")  # Music, and the wavy line, sprig and thistle


def sections(page: str) -> list[dict]:
    """Every numbered section, in book order: {"key": "1.2.4", "book": 1, "book_title": "The Realm of Faerie",
    "chapter": 2, "section": 4, "topics": its chapter's list of topics, "text", "images": [{"url", "caption"}]}."""
    body = page[page.rindex("<h2", 0, page.index('<a id="book1">')):page.index('<a id="index">')]
    heads = list(HEADING.finditer(body))
    found, book, book_title, chapter, topics = [], 0, "", 0, []
    for i, head in enumerate(heads):
        content = body[head.end():heads[i + 1].start() if i + 1 < len(heads) else len(body)]
        level, text = head[1], gutenberg.html_text(head[2])
        if level == "2":  # "BOOK I.\nTHE REALM OF FAERIE."
            book, book_title, chapter = book + 1, gutenberg.titled(text.split("\n")[-1]), 0
        elif level == "3":
            chapter += 1
            summary = re.search(r'<p class="hang">(.*?)</p>', content, re.S)
            topics = [t.strip(" .") for t in gutenberg.html_text(summary[1]).split("—")] if summary else []
        else:
            images = []
            for alt, src in re.findall(r'<img alt="([^"]*)"[^>]*src="([^"]+)"', content):
                if NOT_PICTURES.search(src):
                    continue
                caption = re.search(re.escape(src) + r'.*?<p class="caption">(.*?)</p>', content, re.S)
                shown = gutenberg.html_text(caption[1]) if caption else html.unescape(alt)
                images.append({"url": IMAGES + src,  # "ROWLI AND THE ELLYLL." is "Rowli and the Ellyll"
                               "caption": gutenberg.titled(shown) if shown.isupper() else shown})
            number = roman.to_int(text.rstrip("."))
            found.append({"key": f"{book}.{chapter}.{number}", "book": book, "book_title": book_title,
                          "chapter": chapter, "section": number, "topics": topics,
                          "text": gutenberg.html_text(content), "images": images})
    return found


def build(page: str, curation: dict) -> dict:
    """The sections on the allowlist, in book order, each with its title and other names; and any listed that
    aren't in the book."""
    found = {s["key"]: s for s in sections(page)}
    tales = [{**{k: v for k, v in found[key].items() if k != "topics"}, "title": kept["title"],
              "also": kept.get("also", [])}
             for key, kept in curation["keep"].items() if key in found]
    tales.sort(key=lambda t: (t["book"], t["chapter"], t["section"]))
    return {"tales": tales, "missing": sorted(set(curation["keep"]) - set(found))}


def main() -> None:
    page = gutenberg.download(BOOK, html=True)
    curation = json.loads(CURATION.read_text(encoding="utf-8"))
    data = build(page, curation)
    missing = data.pop("missing")
    (gutenberg.LIB / "goblin.json").write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(data['tales'])} tales kept of {len(sections(page))} sections.")
    if missing:
        print("In the curation but not found in the book:", ", ".join(missing))
        sys.exit(1)


if __name__ == "__main__":
    main()
