"""Builds ktdi/lib/bread.json, the questions for /bread, from the old books the bot already has.

    python -m ktdi.tools.bread_build

Two kinds of question, both from books already curated (so nothing here is new to the bot):

- Built from the books: what a lost word (Mackay), a bit of 1811 slang (Grose), a Bierce definition, a Brewer phrase or
  a flower (Dumont) meant. The right answer is the entry's own meaning, cut to its first sense; the three wrong ones
  are other entries' meanings from the same book, of about the same length, so they sound right too. Only entries
  with a short, clear meaning that doesn't give the word away make a question.
- Scenarios, written by hand from a passage ("If you were a Victorian gentleman passing a lady you'd met once, what
  would you do?"): in ktdi/lib/bread_curation.json's "scenarios", each with the book, the passage it's from, the
  answer the book gives, three wrong answers and (optionally) a note for the findings. The build checks each one's
  passage is in its book.

bread_curation.json's "leave_out" names built questions (by id, with why) that don't make a fair question, or
break a house rule, from reading every one; their answers aren't offered as wrong ones either. Anything that
breaks the house rules is left out by word as well (LEAVE_OUT_WORDS), on top of the books' own curation: a question
takes an entry out of its context, so this is stricter than the books.
"""

import json
import random
import re
from pathlib import Path

LIB = Path(__file__).resolve().parent.parent / "lib"
OUT = LIB / "bread.json"
CURATION = LIB / "bread_curation.json"
SHORTEST, LONGEST = 8, 80  # An answer's length: it has to fit a line, and say something
# Out of context, these read as jabs at people, or worse. (America: the bot never mocks it; Bierce often did.)
# Out of context, these read as jabs at people, or worse: America (the bot never mocks it; Bierce often did), women,
# sex, peoples and faiths, disability and bodies, and cruelty, executions and violence. A wrong answer comes from the
# same entries, so none of these is ever offered as one either.
LEAVE_OUT_WORDS = re.compile(
    r"americ|yankee|\bwom[ae]n\b|\bwi(fe|ves)\b|\bgirls?\b|lad(y|ies)|female|maid|mistress|whore|harlot|bawd|"
    r"wench|strumpet|prostitut|concubin|cuckold|adulter|bastard|\bsex|lewd|lust|\bnaked|venere|\bpox\b|"
    r"suicid|kill(s|ed)? (him|her)self|murder|\bhang(s|ed|ing|man)?\b|gallows|gibbet|tyburn|execut|tortur|"
    r"\bbrand(s|ed|ing)?\b|burn(ing|t|ed)? (culprits|in the hand)|\bbeat(s|en|ing)?\b|flog|whip|stab|"
    r"negro|\bblacks?\b|\bjews?\b|jewish|gyps|\bturks?\b|\bmoors?\b|\bindians?\b|savage|irish|\bscot|welsh|"
    r"dutch|french|\bspani|italian|russian|german|chin(a|ese)man|chinese|\bchrist|trinit|jesus|\bgod\b|deity|"
    r"divin|bible|church|\bpope|papist|catholic|protestant|methodist|quaker|presbyter|heathen|pagan|infidel|"
    r"mahomet|mohammed|muslim|hindu|buddh|effeminate|eunuch|hermaphrod|\bblind\b|\bdeaf\b|\bdumb\b|idiot|"
    r"lunatic|madman|cripple|\blame\b|\bfat\b|ugly|deformed|hunchback|dwarf", re.IGNORECASE)
STOP_WORDS = {"a", "an", "the", "of", "to", "in", "on", "out", "and", "or", "for", "by", "with", "as", "at", "be",
              "is", "it", "his", "her", "its", "up", "no", "not", "all", "one", "two"}
ABBREVIATIONS = re.compile(r"\b(Mr|Mrs|Dr|St|viz|etc|i\.e|e\.g|cf|No)\.", re.IGNORECASE)
LEAD_INS = re.compile(r"^(meaning that|meaning|i\.e\.|that is,?|signifying|a term for|a cant (word|term|name) for)\s+",
                      re.IGNORECASE)
LATIN = re.compile(r"^[A-Z][a-zæœ]+ [a-zæœ]+$")  # "Achillea millefolia": not a name people know


def first_sense(text: str) -> str:
    """An entry's first sense: its first sentence (or clause before a semicolon), tidied."""
    text = ABBREVIATIONS.sub(lambda m: m.group(1) + "\u2024", " ".join(str(text).replace("_", "").split()))  # Mrs.
    match = re.match(r"(.+?)(?:[.;:!?](?:\s|$)|$)", text)
    sense = LEAD_INS.sub("", (match.group(1) if match else text).strip(" ,")).replace("\u2024", ".")
    return sense[:1].upper() + sense[1:] if sense else sense


def fair(word: str, answer: str) -> bool:
    """Whether a meaning makes a fair answer: short, and not giving the word away (nor pointing elsewhere)."""
    if not SHORTEST <= len(answer) <= LONGEST or re.search(r"\bsee\b|\bvide\b|\bditto\b", answer, re.IGNORECASE):
        return False
    if answer.lower().startswith("or ") or re.search(r"\b[A-Z]{3,}\b", answer):  # Grose's "Or HAMCASES": a pointer
        return False
    stems = [w.lower()[:4] for w in re.findall(r"[A-Za-z]{4,}", word)]
    if any(stem in answer.lower() for stem in stems):
        return False
    content = {w.lower() for w in re.findall(r"[A-Za-z]{3}", word)} - STOP_WORDS  # "Two to one, bar one": "Bar…"
    return not any(re.search(rf"\b{w}", answer, re.IGNORECASE) for w in content)


def words_of(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[A-Za-z]{4,}", text)} - {"with", "that", "this", "from", "which", "have"}


def wrong_answers(answer: str, others: list[str], rng: random.Random) -> list[str]:
    """Three other answers from the same book: about the same length, and not sharing words with the right one (so
    none of them is right as well)."""
    close = [o for o in others if o != answer and len(answer) / 2 <= len(o) <= len(answer) * 2
             and not words_of(o) & words_of(answer)]
    pool = close if len(close) >= 3 else [o for o in others if o != answer]
    chosen: list[str] = []
    for other in rng.sample(pool, len(pool)):
        if other.lower() not in (c.lower() for c in chosen) and not words_of(other) & set().union(*map(words_of, chosen)):
            chosen.append(other)
        if len(chosen) == 3:
            return chosen
    return chosen


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def built(kind: str, entries: list[tuple[str, str, str, str]], ask: str, source: str, leave_out: set[str],
          not_asked: set[str] = frozenset(), words: int = 1) -> list[dict]:
    """Questions from (word as shown, answer, link, note) entries, asked as `ask` (with {word}); an answer has at
    least `words` words (a phrase's meaning isn't a lone name: "Voltaire"). A question left out (`leave_out`, by id)
    doesn't lend its answer as a wrong one to the others either: what was garbled or broke a rule stays out. One
    that's only `not_asked` (a wrong answer it drew is arguably right too, or its wording is best avoided) isn't
    asked, but still lends its answer: so leaving it out doesn't redraw everyone else's wrong answers."""
    entries = [e for e in entries if fair(e[0], e[1]) and len(e[1].split()) >= words
               and not LEAVE_OUT_WORDS.search(f"{e[0]} {e[1]} {e[3]}")]
    keyed, seen = [], set()
    for entry in entries:
        key, n = f"{kind}:{slug(entry[0])}", 1
        while key in seen:  # A word the book has twice (two senses, two entries): numbered in book order
            n += 1
            key = f"{kind}:{slug(entry[0])}-{n}"
        seen.add(key)
        if key not in leave_out:
            keyed.append((key, *entry))
    answers = [answer for _, _, answer, _, _ in keyed]
    questions = []
    for key, word, answer, link, note in keyed:
        if key in not_asked:
            continue
        wrong = wrong_answers(answer, answers, random.Random(f"{kind}:{word}:{answer}"))
        if len(wrong) == 3:
            questions.append({"id": key, "kind": kind, "question": ask.format(word=word),
                              "answer": answer, "wrong": wrong, "source": source, "link": link,
                              "note": note if note and note != answer else None})
    return questions


def from_the_books(leave_out: set[str] = frozenset(), not_asked: set[str] = frozenset()) -> list[dict]:
    from ktdi.features import deadword, devils, flower, phrase, slang

    questions = built("lostword", [(e["word"], first_sense(e["meaning"]), deadword.url(e), e["meaning"])
                                   for e in deadword.WORDS],
                      "What did the lost word *{word}* mean?", deadword.SOURCE, leave_out, not_asked)
    questions += built("slang", [(slang.shown_word(e["word"]), first_sense(e["text"]), slang.url(e), e["text"])
                                 for e in slang.ENTRIES if " or " not in e["word"].lower()],
                       "In 1811 slang, what was meant by *{word}*?", slang.SOURCE, leave_out, not_asked)
    questions += built("bierce", [(e["word"].title(), first_sense(e["text"]), devils.url(e), None)
                                  for e in devils.ENTRIES],
                       "How did Ambrose Bierce define *{word}*?", devils.SOURCE, leave_out, not_asked)
    questions += built("phrase", [(e["phrase"], first_sense(e["text"]), phrase.url(e), e["text"])
                                  for e in phrase.PHRASES],
                       "What did the Victorians mean by *{word}*?", phrase.SOURCE, leave_out, not_asked, words=2)
    named = [f for f in flower.FLOWERS if not LATIN.match(f["name"]) and f["meanings"]]
    questions += built("flower", [(f["name"], "; ".join(f["meanings"]), flower.url(f) if f.get("anchor") or f.get("text")
                                   else flower.PAGE, None) for f in named],
                       "In the Victorian language of flowers, what did *{word}* say?", flower.SOURCE, leave_out, not_asked)
    return questions


def scenario_passages() -> dict[str, dict[str, tuple[str, str, str]]]:
    """The passages scenarios can come from, by book and key: (text, link, source). Keys: an etiquette rule's number
    in etiquette.json ("12"), an omen's key ("3.5.2"), an almanac passage's day and number ("10-31:0")."""
    from ktdi.lib import links
    from ktdi.features import almanac, etiquette, omen

    rules = {str(i): (r["text"], links.gutenberg(etiquette.BOOKS[r["book"]][1], r["text"]), etiquette.BOOKS[r["book"]][0])
             for i, r in enumerate(etiquette.RULES)}
    omens = {o["key"]: (o["text"], omen.url(o), omen.SOURCE) for o in omen.OMENS}
    days = {f"{day}:{n}": (p["text"], almanac.url(p), almanac.SOURCE)
            for day, entry in almanac.DAYS.items() for n, p in enumerate(entry.get("passages", []))}
    return {"etiquette": rules, "omen": omens, "almanac": days}


def scenarios(curation: dict) -> list[dict]:
    """The hand-written ones, each checked against its passage."""
    passages = scenario_passages()
    questions = []
    for s in curation.get("scenarios", []):
        found = passages[s["book"]].get(s["entry"])
        assert found, f"{s['id']}: no {s['book']} passage {s['entry']!r}"
        assert len(s["wrong"]) == 3 and s["answer"] not in s["wrong"], s["id"]
        _, link, source = found
        questions.append({"id": s["id"], "kind": s["book"], "question": s["question"], "answer": s["answer"],
                          "wrong": s["wrong"], "source": source, "link": link, "note": s.get("note")})
    return questions


def build() -> dict:
    curation = json.loads(CURATION.read_text(encoding="utf-8")) if CURATION.exists() else {}
    leave_out = set(curation.get("leave_out", {}))  # id: why
    not_asked = set(curation.get("not_asked", {}))  # id: why (a wrong answer it drew is arguably right too...)
    questions = from_the_books(leave_out, not_asked) + scenarios(curation)
    ids = [q["id"] for q in questions]
    assert len(ids) == len(set(ids)), "two questions with one id"
    return {"_about": "The questions for /bread (How well do you 🍞?), built by ktdi/tools/bread_build.py from "
                      "the old books: don't edit by hand.", "questions": questions}


def main() -> None:
    data = build()
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    kinds: dict[str, int] = {}
    for q in data["questions"]:
        kinds[q["kind"]] = kinds.get(q["kind"], 0) + 1
    print(f"{len(data['questions'])} questions: " + ", ".join(f"{k} {n}" for k, n in sorted(kinds.items())))


if __name__ == "__main__":
    main()
