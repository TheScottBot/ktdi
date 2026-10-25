"""Builds ktdi/lib/crust.json, the cards for Crust (/play game:crust), from ktdi/lib/crust_curation.json.

    python -m ktdi.tools.crust_build          (the cards)
    python -m ktdi.tools.crust_build --pool   (writes private/crust/pool.json, the words cards can be made from)

A card is a theme and eight old words that could all fit it, each with its meaning and where it's from. The words
come only from /bread's questions (ktdi/lib/bread.json), which were all read and reviewed against the house rules:
lost words (Mackay), 1811 slang (Grose) and the language of flowers (Dumont). The curation file names each card's
words by their /bread question ids ("lostword:bever"), so a word's meaning and link always come from the book.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
LIB = ROOT / "ktdi" / "lib"
OUT = LIB / "crust.json"
CURATION = LIB / "crust_curation.json"
POOL = ROOT / "private" / "crust" / "pool.json"
KINDS = ("lostword", "slang", "flower")  # Words with a meaning to clue: not Bierce's (everyone knows those words)


def pool() -> dict[str, dict]:
    """Every word a card can use, by its /bread question id: {word, meaning, kind, source, link}."""
    questions = json.loads((LIB / "bread.json").read_text(encoding="utf-8"))["questions"]
    words = {}
    for q in questions:
        if q["kind"] in KINDS:
            word = re.search(r"\*(.+?)\*", q["question"]).group(1)
            words[q["id"]] = {"word": word, "meaning": q["answer"], "kind": q["kind"], "source": q["source"],
                              "link": q["link"]}
    return words


def build() -> dict:
    curation = json.loads(CURATION.read_text(encoding="utf-8"))
    words = pool()
    cards = []
    for card in curation["cards"]:
        assert len(card["words"]) == 8 and len(set(card["words"])) == 8, card["id"]
        missing = [word_id for word_id in card["words"] if word_id not in words]
        assert not missing, f"{card['id']}: not in /bread's reviewed words: {missing}"
        entries = [{key: words[word_id][key] for key in ("word", "meaning", "source", "link")}
                   for word_id in card["words"]]
        assert len({e["word"].casefold() for e in entries}) == 8, f"{card['id']}: a word twice"
        cards.append({"id": card["id"], "theme": card["theme"], "words": entries})
    ids = [card["id"] for card in cards]
    assert len(ids) == len(set(ids)), "two cards with one id"
    return {"_about": "Crust's cards (/play game:crust), built by ktdi/tools/crust_build.py from crust_curation.json: "
                      "don't edit by hand.", "cards": cards}


def main() -> None:
    if "--pool" in sys.argv:
        POOL.parent.mkdir(parents=True, exist_ok=True)
        words = pool()
        POOL.write_text(json.dumps(words, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{len(words)} words in {POOL}")
        return
    data = build()
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(data['cards'])} cards")


if __name__ == "__main__":
    main()
