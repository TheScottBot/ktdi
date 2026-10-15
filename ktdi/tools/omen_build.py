"""Build /omen's superstitions from Robert Means Lawrence's The Magic of the Horse-shoe, with Other Folk-Lore Notes
(1898; public domain, Project Gutenberg 57411): python -m ktdi.tools.omen_build

Lawrence, a Boston physician, collected the everyday superstitions hiding in plain sight: why a horseshoe is lucky,
spilling salt, blessing a sneeze, unlucky Fridays, rats served with legal notices, the luck of odd numbers and the
ill luck of thirteen. The book is seven essays, each in numbered subsections; the subsections run to pages, so what's
kept is a paragraph, or a short run of them (one omen or custom and its explanation), filed under its subsection.

ktdi/lib/omen_curation.json gives each one kept a title of its own and other names to look it up by:
{"keep": {"3.5.2": {"title": "Spilling Salt", "also": [...], "to": 4}}}, keyed essay.subsection.paragraph (counted
from 1), with "to" for a run (here paragraphs 2 to 4). The book was read once, and its dull stretches and what's 1898
at its worst left out. Writes ktdi/lib/omen.json.

To add one, read it in the book, then add its key and a title to "keep".
"""

import json
import re
import sys

from ktdi.lib import roman
from ktdi.tools import gutenberg

BOOK = 57411
CURATION = gutenberg.curation_file("omen")
HEADING = re.compile(r"<h([23])\b[^>]*>(.*?)</h\1>", re.S)


def paragraphs(page: str) -> list[dict]:
    """Every paragraph of the essays, in book order: {"key": "3.5.2", "essay": 3, "essay_title": "The Folk-Lore of
    Common Salt", "section": 5, "section_title": "Salt-Spilling as an Omen", "paragraph": 2, "text"}. An essay's
    motto, before its first subsection, isn't one."""
    start = page.rindex("<h2", 0, page.index('id="THE_MAGIC_OF_THE_HORSE-SHOE"'))
    body = page[start:page.index("<h2>FOOTNOTES</h2>")]
    heads = list(HEADING.finditer(body))
    found, essay, essay_title = [], 0, ""
    for i, head in enumerate(heads):
        content = body[head.end():heads[i + 1].start() if i + 1 < len(heads) else len(body)]
        title = " ".join(gutenberg.html_text(head[2]).split())
        if head[1] == "2":
            essay, essay_title = essay + 1, gutenberg.titled(re.sub(r"\[\d+\]", "", title))
            continue
        number, section_title = title.split(" ", 1)  # "V. SALT-SPILLING AS AN OMEN"
        section = roman.to_int(number.rstrip("."))
        for n, text in enumerate(gutenberg.html_text(content).split("\n\n"), start=1):
            found.append({"key": f"{essay}.{section}.{n}", "essay": essay, "essay_title": essay_title,
                          "section": section, "section_title": gutenberg.titled(section_title), "paragraph": n,
                          "text": text})
    return found


def build(page: str, curation: dict) -> dict:
    """The paragraphs on the allowlist, in book order, each with its title and other names; and any listed that
    aren't in the book."""
    found = {p["key"]: p for p in paragraphs(page)}
    omens, missing = gutenberg.titled_keep(found, curation)
    for omen in omens:  # A run of paragraphs: from the key's to "to" (an omen, then its explanation)
        last = curation["keep"][omen["key"]].get("to")
        if last:
            run = [found.get(f"{omen['essay']}.{omen['section']}.{n}") for n in range(omen["paragraph"], last + 1)]
            if None in run:
                missing.append(f"{omen['key']} to {last}")
            omen["text"] = "\n\n".join(p["text"] for p in run if p)
    return {"omens": omens, "missing": missing}


def main() -> None:
    page = gutenberg.download(BOOK, html=True)
    curation = json.loads(CURATION.read_text(encoding="utf-8"))
    data = build(page, curation)
    missing = data.pop("missing")
    (gutenberg.LIB / "omen.json").write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(data['omens'])} omens kept of {len(paragraphs(page))} paragraphs.")
    if missing:
        print("In the curation but not found in the book:", ", ".join(missing))
        sys.exit(1)


if __name__ == "__main__":
    main()
