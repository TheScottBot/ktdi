"""Finding the ailment someone means, however they put it: "tickly throat", "my throat is tickly", "diarhea".

No AI: the names in ktdi/lib/ailments.py, compared word by word (any order, small typos allowed), then as whole
phrases for anything that got past that. Returns None for things nobody could match ("dave"); /cure then falls back on
All-heal.
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import cache

from ktdi.lib.ailments import AILMENTS, Ailment

# Words that don't change what's wrong with you.
FILLER = {
    "i", "im", "ive", "id", "me", "my", "mine", "a", "an", "the", "of", "for", "with", "from", "to", "in", "on", "at",
    "it", "its", "this", "that", "and", "is", "am", "are", "was", "be", "been", "have", "has", "had", "got", "get",
    "getting", "gotten", "some", "bit", "little", "bad", "badly", "really", "very", "so", "too", "proper", "mega",
    "severe", "mild", "slight", "terrible", "awful", "horrible", "nasty", "cure", "cures", "remedy", "help", "please",
    "case", "feeling", "feel", "feels", "what", "whats", "how", "do", "does", "should", "cure", "suffering",
}
GOOD_ENOUGH = 0.6


@dataclass
class Match:
    ailment: Ailment
    name: str  # The name it matched ("tickly throat"), which may not be the ailment's main one.
    exact: bool


def words(text: str) -> list[str]:
    text = text.lower().replace("’", "'").replace("'", "")
    return [w for w in re.sub(r"[^a-z0-9]+", " ", text).split() if w not in FILLER]


def same_word(a: str, b: str) -> bool:
    if a == b or a.rstrip("s") == b.rstrip("s"):
        return True
    return min(len(a), len(b)) >= 4 and SequenceMatcher(None, a, b).ratio() >= 0.8


@cache
def index() -> list[tuple[Ailment, str, tuple[str, ...]]]:
    return [(ailment, name, tuple(words(name))) for ailment in AILMENTS for name in ailment.names if words(name)]


def score(query: list[str], name: list[str]) -> float:
    """How well the words typed cover a name (and how few typed words go unused), allowing typos."""
    found_in_name = sum(any(same_word(w, n) for w in query) for n in name)
    used_from_query = sum(any(same_word(w, n) for n in name) for w in query)
    coverage, precision = found_in_name / len(name), used_from_query / len(query)
    if coverage < 0.5:
        return 0.0
    return 0.65 * coverage + 0.35 * precision


def find(query: str) -> Match | None:
    typed = words(query)
    if not typed:
        return None
    best, best_score = None, 0.0
    for ailment, name, name_words in index():
        if list(name_words) == typed:
            return Match(ailment, name, exact=True)
        by_words = score(typed, list(name_words))
        by_spelling = SequenceMatcher(None, " ".join(typed), " ".join(name_words)).ratio() * 0.95
        if max(by_words, by_spelling) > best_score:
            best, best_score = (ailment, name), max(by_words, by_spelling)
    if best is None or best_score < GOOD_ENOUGH:
        return None
    return Match(best[0], best[1], exact=False)


def suggestions(typed: str, limit: int = 25) -> list[str]:
    """Names for autocomplete: ones starting with what's typed first, then ones containing it."""
    typed = typed.strip().lower()
    names = [name for _, name, _ in index()]
    if not typed:
        return [ailment.name for ailment in AILMENTS][:limit]
    starts = [n for n in names if n.startswith(typed)]
    contains = [n for n in names if typed in n and n not in starts]
    return (starts + contains)[:limit]
