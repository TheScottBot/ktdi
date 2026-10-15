"""Build /wonder's curiosities from Ten Thousand Wonderful Things (ed. Edmund Fillingham King, 1894; public domain,
Project Gutenberg 45849): python -m ktdi.tools.wonder_build

A Victorian cabinet of curiosities: about a thousand short articles ("A LUCKY FIND.", "HOOPS IN 1740.", "FOX KILLED
BY A SWAN.") on remarkable objects, customs, people, inventions and claims, many with an engraving. It's read from
the book's web page rather than its plain text, as that's where the pictures are: each article starts with its
title, centred and in capitals, and keeps its own pictures (the plain text loses a hundred of them).

Each article is numbered in book order (the book doesn't number them: "Wonder No. 312" is ours), and only those in
ktdi/lib/wonder_curation.json are kept, by title (a title the book uses twice is "TITLE (2)" the second time): the
book was read once, and the dull, and what's 1894 at its worst (the racism, the gloating over executions and
torture, cruelty to animals), left out. Writes ktdi/lib/wonder.json.

To add one, read it in the book, then add its title to "keep".
"""

import html
import json
import re
import sys

from ktdi.tools import gutenberg

BOOK = 45849
IMAGES = f"https://www.gutenberg.org/cache/epub/{BOOK}/"  # The page's images are relative to this
CURATION = gutenberg.curation_file("wonder")
FIRST = "PUNISHMENTS IN PROVINCIAL TOWNS IN THE OLDEN TIME."  # The first article (after the indexes)
LAST = "PRINTED BY WILLIAM CLOWES"  # The printer's line after the last
TITLE = re.compile(r'<p class="center">((?:(?!</p>).)*)</p>', re.S)
SMALL_CAPS = re.compile(r'\s*<span class="smcap">([^<]*)(?:<br\s*/?>)?')
RULE = "i_006"  # The decorative line between sections, not a picture of anything
SMALL_WORDS = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "of", "on", "or", "the", "to", "with"}
ROMAN = re.compile(r"^((?=[IVXLC])C{0,3}(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3}))(\.?(?:'S)?,?)$")  # Not "CIVIL"


def plain(fragment: str) -> str:
    """A bit of the page as text: italics as _italics_ (as Gutenberg's plain text has them, so oldbooks.escape shows
    them), raised letters in their word ("y<sup>e</sup>" is "ye"), paragraphs apart, lines of verse and table rows on
    lines of their own, page numbers and captions out."""
    fragment = " ".join(fragment.split())  # The page's own line breaks mean nothing
    fragment = re.sub(r'<span class="pagenum">.*?</span>', "", fragment)
    fragment = re.sub(r'<div class="caption[^"]*">.*?</div>', "", fragment)
    fragment = re.sub(r"<(i|em)\b[^>]*>(.*?)</\1>", lambda m: f"_{m[2].strip()}_" if m[2].strip() else m[2], fragment)
    fragment = re.sub(r'</p>|</table>|<div class="(?:poem|stanza)[^"]*">', "\n\n", fragment)
    fragment = re.sub(r"<br\s*/?>|</tr>|</div>", "\n", fragment)
    fragment = re.sub(r"</t[dh]>\s*<t[dh][^>]*>", " — ", fragment)
    fragment = html.unescape(re.sub(r"<[^>]+>", "", fragment)).replace("\xa0", " ")
    paragraphs = ["\n".join(" ".join(line.split()) for line in block.split("\n") if line.strip())
                  for block in re.split(r"\n\s*\n", fragment)]
    return "\n\n".join(p for p in paragraphs if p)


def titled(title: str) -> str:
    """"FOX KILLED BY A SWAN." is "Fox Killed by a Swan"; "HENRY VIII.'S WALKING STICK" keeps its numerals."""
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


def heading(block: str) -> str | None:
    """A centred block's title, if it's one: in capitals ("A LUCKY FIND."), or its first line in small capitals
    ("may-fair play bill in the time of william iii.", above the playbill itself)."""
    small = SMALL_CAPS.match(block)
    title = " ".join(plain(small[1].upper() if small else block).split())
    return title if re.search(r"[A-Z]{3}", title) and not re.search(r"[a-z]", title) else None


def articles(page: str) -> list[dict]:
    """Every article, in book order: {"number": 1, "key": "A LUCKY FIND.", "title": "A Lucky Find", "text": its
    paragraphs, "images": [{"url", "caption"}]}."""
    body = page[page.index(f'<p class="center">{FIRST}</p>'):page.index(LAST)]
    heads = [(m, title) for m in TITLE.finditer(body) if (title := heading(m[1]))]
    seen: dict[str, int] = {}
    found = []
    for number, (head, title) in enumerate(heads, start=1):
        end = heads[number][0].start() if number < len(heads) else len(body)
        content = body[head.end():end]
        if SMALL_CAPS.match(head[1]):  # The rest of the block is the article's start (the playbill under its title)
            content = head[1][SMALL_CAPS.match(head[1]).end():] + content
        seen[title] = seen.get(title, 0) + 1
        images = [{"url": IMAGES + src, "caption": html.unescape(alt).strip()}
                  for alt, src in re.findall(r'<img alt="([^"]*)"[^>]*src="([^"]+)"', content) if RULE not in src]
        found.append({"number": number, "key": title if seen[title] == 1 else f"{title} ({seen[title]})",
                      "title": titled(title), "text": plain(content), "images": images})
    return found


def build(page: str, curation: dict) -> dict:
    """The articles on the allowlist, in book order, and any listed that aren't in the book."""
    found = articles(page)
    keep = set(curation["keep"])
    return {"wonders": [a for a in found if a["key"] in keep],
            "missing": sorted(keep - {a["key"] for a in found})}


def main() -> None:
    page = gutenberg.download(BOOK, html=True)
    curation = json.loads(CURATION.read_text(encoding="utf-8"))
    data = build(page, curation)
    missing = data.pop("missing")
    (gutenberg.LIB / "wonder.json").write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(data['wonders'])} wonders kept of {len(articles(page))}.")
    if missing:
        print("In the curation but not found in the book:", ", ".join(missing))
        sys.exit(1)


if __name__ == "__main__":
    main()
