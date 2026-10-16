"""Build /flowermeaning's flowers from Henrietta Dumont's The Language of Flowers (1851; public domain, Project
Gutenberg 71779): python -m ktdi.tools.flower_build

The Victorians sent messages in flowers, and books like this one were the dictionary: a pansy is "Think of me",
basil "Hate", an asphodel "My regrets follow you to the grave". This one has a Dictionary of Flowers (about 250, each
with its meaning), a chapter of prose and verse on about a hundred of them, and six coloured plates of bouquets
that spell out whole messages ("Your self-love and stupidity excite my pity"). Each flower is kept with its
meanings, its chapter if it has one, and the plate it's in if it's in one. The meanings are this compiler's: other
books of the day gave others.

Its calendar of flowers (a flower for each day) isn't kept: /almanac has the day's flower from the same tradition.

ktdi/lib/flower_curation.json lists the flowers kept, by name ("keep"), and those whose chapter is left out but
whose meaning is kept ("no_text"). The book was read once, and anything that's 1851 at its worst left out.
Writes ktdi/lib/flowers.json.
"""

import json
import re
import sys

from ktdi.tools import gutenberg

BOOK = 71779
PAGE = f"https://www.gutenberg.org/cache/epub/{BOOK}/pg{BOOK}-images.html"
CURATION = gutenberg.curation_file("flower")
# A chapter's heading: mostly <h2>, but one is a centred line ("MEADOW SAFFRON.... My best days are past.")
CHAPTER = re.compile(r'<h2>(.*?)</h2>|<p class="c">(<span class="smcap">.*?)</p>', re.S)
PLATES = [  # Their captions run the flowers together ("SWEET PEA PANSY"), so they're named here
    ("images/i_004.jpg", ["Rose", "Blue Violet", "Jasmine", "Moss Rose", "Rose Bud"],
     "Your beauty, modesty and amiability, have drawn from me a confession of love."),
    ("images/i_052.jpg", ["Daisy", "Wall-Flower", "Tulip"],
     "Your innocence and fidelity in misfortune have caused me to declare my love for you."),
    ("images/i_114.jpg", ["Mignionette", "Pink", "Pink Bud"],
     "Your qualities surpassing your charms, have drawn from me a confession of pure love."),
    ("images/i_152.jpg", ["Rose Bud", "Yellow Lily", "Lilac"],
     "I confess your majestic beauty has awakened my first emotions of love."),
    ("images/i_207.jpg", ["Sweet Pea", "Pansy"], "I depart. Think on me."),
    ("images/i_259.jpg", ["Narcissus", "Scarlet Geranium", "Marigold"], "Your self-love and stupidity excite my pity."),
]


def norm(name: str) -> frozenset[str]:
    """A flower's name as the words in it, so "Violet, Blue", "Blue Violet" and "blue-violet" are the same."""
    return frozenset(re.findall(r"[a-z]+", name.casefold().replace("-", " ")))


def meaning(text: str) -> str:
    """"Painful Recollections." is "Painful recollections"; "Touch me not." is "Touch me not"."""
    text = " ".join(text.split()).rstrip(".")
    return text[:1] + text[1:].lower() if text.istitle() else text


def same(text: str) -> str:
    """A meaning by its letters alone: "Peace—reconciliation" and "Peace, reconciliation" are the same one."""
    return "".join(c for c in text.casefold() if c.isalpha())


def dictionary(page: str) -> list[tuple[str, str]]:
    """The Dictionary of Flowers as (name, meaning) rows. A row starting "——" is under the one before: "—— Rose"
    under Acacia is "Acacia, Rose", "—— and Cypress" under Marigold is "Marigold and Cypress"; "——" alone is
    the same flower again, with another meaning."""
    table = page[page.index('id="Dictionary_of_Flowers"'):]
    table = table[:table.index("</table>")]
    rows, base, last = [], "", ""
    for name, means in re.findall(r"<tr><td>(.*?)</td><td>(.*?)</td></tr>", table, re.S):
        name, means = gutenberg.html_text(name), meaning(gutenberg.html_text(means))
        if name.startswith("——"):
            rest = name.lstrip("—").strip(" ,")
            name = (f"{base} {rest}" if rest.startswith("and ") else f"{base}, {rest}") if rest else last
        else:
            base = name.split(",")[0]
        last = name
        rows.append((name, means))
    return rows


def chapters(page: str) -> list[dict]:
    """The flowers with a chapter: {"name": "Pansy", "also": [...], "meaning": "Think of me", "text", "anchor"}. A
    heading is "Pansy.... _Think of me_."; one naming two ("Sweet-Brier, or Eglantine") is both."""
    body = page[:page.rindex("<h2", 0, page.index('id="Dictionary_of_Flowers"'))]

    def is_flower(head: re.Match) -> bool:
        """A flower's name is in small capitals (not "Preface", "Contents" or "DEATH OF THE FLOWERS"), and a centred
        line is a heading only with its meaning (not a verse's title, "the country maid")."""
        block = head[1] or head[2]
        return 'class="smcap"' in block and (head[1] is not None or "...." in gutenberg.html_text(block))

    # Every <h2> ends the chapter before it ("DEATH OF THE FLOWERS" too); a verse's centred title doesn't
    heads = [head for head in CHAPTER.finditer(body) if head[1] is not None or is_flower(head)]
    found = []
    for i, head in enumerate(heads):
        if not is_flower(head):
            continue
        block = head[1] or head[2]
        anchor = re.search(r'<a id="([^"]+)">', block)
        title = gutenberg.html_text(block).replace("_", "")
        name, means = (re.split(r"\.\s*\.\.\.+", title.replace(". ...", "...."), maxsplit=1) + [""])[:2]
        names = [n.strip(" .,") for n in re.split(r",? or |, | and ", name) if n.strip(" .,")]
        content = body[head.end():heads[i + 1].start() if i + 1 < len(heads) else len(body)]
        content = re.sub(r'<div class="figcenter".*?</div>', "", content, flags=re.S)  # The plates go with the flower
        found.append({"name": names[0], "also": names[1:], "meaning": meaning(means) if means else "",
                      "anchor": anchor[1] if anchor else None, "text": gutenberg.html_text(content)})
    return found


def flowers(page: str) -> list[dict]:
    """Every flower, from the dictionary and the chapters together, in the dictionary's order (chapter flowers it
    doesn't have, after): {"name", "also", "meanings": [...], "text": its chapter or None, "anchor": the chapter's,
    or the dictionary's, "plate": {"url", "flowers", "message"} or None}."""
    found: dict[frozenset, dict] = {}
    for name, means in dictionary(page):
        flower = found.setdefault(norm(name), {"name": name, "also": [], "meanings": [], "text": None,
                                               "anchor": "Dictionary_of_Flowers", "plate": None})
        if same(means) not in map(same, flower["meanings"]):
            flower["meanings"].append(means)
    for chapter in chapters(page):
        keys = [norm(n) for n in (chapter["name"], *chapter["also"])]
        flower = next((found[k] for k in keys if k in found), None)
        if flower is None:
            flower = found.setdefault(keys[0], {"name": chapter["name"], "also": [], "meanings": [], "plate": None})
        flower["also"] = [n for n in (chapter["name"], *chapter["also"]) if norm(n) != norm(flower["name"])]
        flower["text"], flower["anchor"] = chapter["text"], chapter["anchor"]
        if chapter["meaning"] and same(chapter["meaning"]) not in map(same, flower["meanings"]):
            flower["meanings"].insert(0, chapter["meaning"])
    for src, names, message in PLATES:
        for name in names:
            if norm(name) in found:
                found[norm(name)]["plate"] = {"url": f"https://www.gutenberg.org/cache/epub/{BOOK}/{src}",
                                              "flowers": names, "message": message}
    return list(found.values())


def build(page: str, curation: dict) -> dict:
    """The flowers on the allowlist (those on "no_text" without their chapter); and any listed that aren't in the
    book."""
    found = flowers(page)
    keep, no_text = set(curation["keep"]), set(curation.get("no_text", []))
    kept = [{**f, "text": None if f["name"] in no_text else f["text"]} for f in found if f["name"] in keep]
    return {"flowers": kept, "missing": sorted(keep - {f["name"] for f in found})}


def main() -> None:
    page = gutenberg.download(BOOK, html=True)
    curation = json.loads(CURATION.read_text(encoding="utf-8"))
    data = build(page, curation)
    missing = data.pop("missing")
    (gutenberg.LIB / "flowers.json").write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(data['flowers'])} flowers kept of {len(flowers(page))}.")
    if missing:
        print("In the curation but not found in the book:", ", ".join(missing))
        sys.exit(1)


if __name__ == "__main__":
    main()
