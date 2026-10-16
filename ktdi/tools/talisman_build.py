"""Build /talisman's passages from William Thomas and Kate Pavitt's The Book of Talismans, Amulets and Zodiacal Gems
(1914; second edition 1922; Project Gutenberg 78789): python -m ktdi.tools.talisman_build

The Pavitts, a London maker of talismanic jewellery and his wife, a Theosophist, wrote it as believers: Part I is
the talismans of the world (the axe and the arrow-head, the Chinese and Japanese, the Egyptian ankh and scarab, the
Gnostic and the medieval, the pentagram and Abracadabra), Part II a chapter for each sign of the zodiac, with its
stones, its planet and the famous gems that go with it. They died in 1937 and 1949, so it's out of copyright in the
UK too.

The chapters run to pages, so what's kept is a paragraph, or a short run of them, filed under its chapter.
ktdi/lib/talisman_curation.json gives each one kept a title of its own and other names to look it up by:
{"keep": {"2.1.12": {"title": "The Hope Diamond", "also": ["diamond", "aries"], "to": 13}}}, keyed
part.chapter.paragraph (counted from 1; a chapter's list of contents isn't one). The book was read once, and what's
1922 at its worst left out, and every health claim (the book makes them as advice).

The book's plates are drawings of the talismans, numbered; a passage that cites one ("No. 16 (Plate I)") shows it,
and the zodiac chapters show the frontispiece, the gems and glyphs of the signs. Plates I and II (with swastikas),
VI and VIII (with amulets that break the house rules) are never shown. Writes ktdi/lib/talismans.json.
"""

import json
import re
import sys

from ktdi.tools import gutenberg

BOOK = 78789
CURATION = gutenberg.curation_file("talisman")
IMAGES = f"https://www.gutenberg.org/cache/epub/{BOOK}/images/"
HEADING = re.compile(r"<h([234])\b[^>]*>(.*?)</h\1>", re.S)
PLATES = {  # The plates that may be shown, by number, with their captions; and the frontispiece
    3: "Chinese and Japanese Talismans", 4: "Egyptian Talismans", 5: "Egyptian Talismans",
    7: "Egyptian and Gnostic Talismans", 9: "Early Christian and Mediæval Talismans", 10: "Mediæval Talismans"}
FRONTISPIECE = {"url": IMAGES + "frontpiece.jpg", "caption": "Gems, Symbols, and Glyphs of the Zodiac"}
CITED = re.compile(r"\bPlate ([IVX]+)\b|\bFrontispiece\b")
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10}


def book(page: str) -> str:
    """Parts I and II, pictures and each chapter's list of contents out."""
    body = page[page.rindex("<h2", 0, page.index('id="PART_I"')):page.rindex("<h2", 0, page.index('id="BIBLIOGRAPHY"'))]
    body = re.sub(r"<figure.*?</figure>", "", body, flags=re.S)
    return re.sub(r'<p class="hanging2">.*?</p>', "", body, flags=re.S)


def paragraphs(page: str) -> list[dict]:
    """Every paragraph of the book, in order: {"key": "2.1.12", "part": 2, "chapter": 1, "paragraph": 12, "where":
    "Aries—The Ram"}. A heading inside a chapter ("General Talismans") doesn't start a new one."""
    body = book(page)
    heads = list(HEADING.finditer(body))
    found, part, chapter, where, n = [], 0, 0, "", 0
    for i, head in enumerate(heads):
        title = " ".join(gutenberg.html_text(head[2]).split())
        content = body[head.end():heads[i + 1].start() if i + 1 < len(heads) else len(body)]
        if title.startswith("PART"):
            part, chapter = part + 1, 0
            continue
        if title.startswith("CHAPTER"):
            chapter, n = chapter + 1, 0
            sign = title.split(" ", 2)[2] if part == 2 and title.count(" ") >= 2 else ""
            where = gutenberg.titled(sign) if sign else f"Talismans and Amulets, Chapter {title.split()[1]}"
        for text in (p for p in gutenberg.html_text(content).split("\n\n") if p):
            n += 1
            found.append({"key": f"{part}.{chapter}.{n}", "part": part, "chapter": chapter, "paragraph": n,
                          "where": where, "text": re.sub(r"^([A-Z])([A-Z’']+)\b(?=\s+[a-z])",
                                                         lambda m: m[1] + m[2].lower(), text)})
    return found


def picture(passage: dict) -> dict | None:
    """The plate the passage cites first, if it may be shown; else, in Part II, the zodiac frontispiece."""
    for cited in CITED.finditer(passage["text"]):
        if cited[0] == "Frontispiece":
            return FRONTISPIECE
        number = ROMAN.get(cited[1])
        if number in PLATES:
            return {"url": f"{IMAGES}plate_{number}.jpg", "caption": f"Plate {cited[1]}: {PLATES[number]}"}
    return FRONTISPIECE if passage["part"] == 2 else None


def build(page: str, curation: dict) -> dict:
    """The paragraphs on the allowlist, in book order, each with its title, other names and picture; and any listed
    that aren't in the book."""
    talismans, missing = gutenberg.titled_keep({p["key"]: p for p in paragraphs(page)}, curation)
    for talisman in talismans:
        talisman["picture"] = picture(talisman)
        for field in ("part", "chapter", "paragraph"):
            del talisman[field]
    return {"talismans": talismans, "missing": missing}


def main() -> None:
    page = gutenberg.download(BOOK, html=True)
    curation = json.loads(CURATION.read_text(encoding="utf-8"))
    data = build(page, curation)
    missing = data.pop("missing")
    (gutenberg.LIB / "talismans.json").write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(data['talismans'])} passages kept of {len(paragraphs(page))} paragraphs.")
    if missing:
        print("In the curation but not found in the book:", ", ".join(missing))
        sys.exit(1)


if __name__ == "__main__":
    main()
