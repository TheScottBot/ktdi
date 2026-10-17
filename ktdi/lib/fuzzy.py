"""Finding what someone means, however they type it: the loose matching behind /cure, /plant, /vulgartongue,
/deadword, !devils, !dream, !phrase, /pliny and /etiquette. No AI.

A name matches what was typed word by word, in any order, with small typos allowed ("my throat is tickly" finds
"tickly throat", "diarhea" finds "diarrhoea"), or failing that as a whole phrase spelt nearly the same. Filler words
("the", "my", "really", "help") are ignored. Nothing close enough: None.

Typical use: build an index of (thing, name) once, then best_match(typed, index) for the best thing, starting_first()
for autocomplete, and containing() for "which entries use this word" ("drunk" finds every word for drunk).
"""

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable, Generic, Iterable, TypeVar

T = TypeVar("T")

# Words that don't change what someone means.
FILLER = {
    "i", "im", "ive", "id", "me", "my", "mine", "a", "an", "the", "of", "for", "with", "from", "to", "in", "on", "at",
    "it", "its", "this", "that", "and", "is", "am", "are", "was", "be", "been", "have", "has", "had", "got", "get",
    "getting", "gotten", "some", "bit", "little", "bad", "badly", "really", "very", "so", "too", "proper", "mega",
    "severe", "mild", "slight", "terrible", "awful", "horrible", "nasty", "cure", "cures", "remedy", "help", "please",
    "case", "feeling", "feel", "feels", "what", "whats", "how", "do", "does", "should", "suffering",
}
GOOD_ENOUGH = 0.6  # The lowest score that counts as a match.
SPELLING = 0.95  # How much a whole-phrase spelling match counts, against a word-by-word one...
STRICT_SPELLING = 0.85  # ...or for short names that look alike ("dave" is nearly "avens" and "dance").
SPELT_ALIKE = 0.75  # How alike a whole phrase's spelling must be to count ("candel"/"candles" 0.77; "pegasus"/"peas" 0.73)
TYPO = 0.75  # How much a word a small typo away counts, against the word itself


@dataclass
class Found(Generic[T]):
    thing: T
    name: str  # The name it matched, which may not be the thing's main one ("tickly throat" for sore throat).
    exact: bool  # Typed as that name, filler aside ("a tickly throat"), not just close to it.


Index = list[tuple[T, str, tuple[str, ...]]]  # (thing, name, the name's words)


LIGATURES = str.maketrans({"æ": "ae", "œ": "oe", "ß": "ss"})


def plain(text: str) -> str:
    """Lower case, in plain letters: old books write "Æthiopia" and "phœnix", and "Châteaux"; people type "aethiopia",
    "phoenix" and "chateaux"."""
    text = unicodedata.normalize("NFKD", text.casefold().translate(LIGATURES))
    return "".join(c for c in text if not unicodedata.combining(c))


def words(text: str) -> list[str]:
    """The words that matter: lower case, no punctuation, no filler. "I've got a TICKLY throat!" -> tickly, throat."""
    text = plain(text).replace("’", "'").replace("'", "")
    return [w for w in re.sub(r"[^a-z0-9]+", " ", text).split() if w not in FILLER]


def singular(word: str) -> str:
    return word[:-3] + "y" if word.endswith("ies") and len(word) > 4 else word.rstrip("s")  # "daisies", "boils"


def same_word(a: str, b: str) -> bool:
    """The same word, a plural of it, or (four letters or more, starting the same) a small typo away. People rarely
    mistype a word's first letter, so "ginger" isn't a typo of "finger", nor "teath" of "death"."""
    if a == b or singular(a) == singular(b):
        return True
    return min(len(a), len(b)) >= 4 and a[0] == b[0] and SequenceMatcher(None, a, b).ratio() >= 0.8


def word_match(a: str, b: str) -> float:
    """1 for the same word (or its plural), TYPO for one a small typo away, 0 otherwise. A typo counts for less, so
    "ginger" (one letter off "finger") can't win "finger nails" on its own."""
    if a == b or singular(a) == singular(b):
        return 1.0
    return TYPO if same_word(a, b) else 0.0


def score(query: list[str], name: list[str]) -> float:
    """How well the words typed cover a name (and how few typed words go unused), allowing typos."""
    found_in_name = sum(max(word_match(w, n) for w in query) for n in name)
    used_from_query = sum(max(word_match(w, n) for n in name) for w in query)
    coverage, precision = found_in_name / len(name), used_from_query / len(query)
    if coverage < 0.5:
        return 0.0
    return 0.65 * coverage + 0.35 * precision


def index(pairs: Iterable[tuple[T, str]]) -> Index:
    """(thing, name) pairs ready for best_match. Names that are all filler are left out."""
    return [(thing, name, tuple(words(name))) for thing, name in pairs if words(name)]


def best_match(query: str, entries: Index, spelling: float = SPELLING) -> Found | None:
    """The thing whose name best matches what was typed, or None if nothing's close enough. An exact match (the
    name's words in its order, filler aside) wins outright; the same words in another order are a close match."""
    typed = words(query)
    if not typed:
        return None
    best, best_score = None, 0.0
    for thing, name, name_words in entries:
        if list(name_words) == typed:
            return Found(thing, name, True)
        by_words = score(typed, list(name_words))
        spelt, name_spelt = " ".join(typed), " ".join(name_words)
        alike = SequenceMatcher(None, spelt, name_spelt).ratio() if spelt[0] == name_spelt[0] else 0.0
        by_spelling = alike * spelling if alike >= SPELT_ALIKE else 0.0  # "pegasus" is only 73% "peas": no
        if max(by_words, by_spelling) > best_score:
            best, best_score = (thing, name), max(by_words, by_spelling)
    if best is None or best_score < GOOD_ENOUGH:
        return None
    return Found(best[0], best[1], False)


def starting_first(typed: str, items: list[T], limit: int = 25, key: Callable[[T], str] = str) -> list[T]:
    """For autocomplete: the items whose name starts with what's typed, then the ones whose name contains it, in
    their own order within each. `key` gets an item's name (items are names already, by default)."""
    typed = plain(typed.strip())
    starts = [item for item in items if plain(key(item)).startswith(typed)]
    contains = [item for item in items if typed in plain(key(item)) and not plain(key(item)).startswith(typed)]
    return (starts + contains)[:limit]


@dataclass
class LookUp(Generic[T]):
    """What look_up found: the entry for the word ("exact"), the entries that use it ("uses"), or an entry spelt
    like it ("close")."""
    kind: str
    entries: list[T]


def look_up(query: str, entries: Index, items: list[T], text: Callable[[T], str], meaning_first: bool = True,
            spelling: float = STRICT_SPELLING, close_first: bool = False) -> LookUp | None:
    """A dictionary lookup, as the 📜 Old books commands do it: the word's own entry if it's a headword; otherwise the
    entries whose text uses it ("drunk" finds every word for drunk); otherwise an entry spelt like it; otherwise None.
    With close_first, an entry close to what was typed comes before the ones that use it: for idioms, where "raining
    cats and dogs" means the entry "To rain cats and dogs", not every entry that mentions cats."""
    match = best_match(query, entries, spelling=spelling)
    if match and match.exact:
        return LookUp("exact", [match.thing])
    if match and close_first:
        return LookUp("close", [match.thing])
    found = containing(query, items, text, meaning_first)
    if found:
        return LookUp("uses", found)
    return LookUp("close", [match.thing]) if match else None


def containing(query: str, items: list[T], text: Callable[[T], str], meaning_first: bool = True) -> list[T]:
    """Items whose text uses every word typed, or a longer form of it ("drunk" finds "drunkard"). With meaning_first,
    items that use them in the first part of their text (before the first . or ;) are what they mean, so only those
    are returned if there are any; ones that only mention them in passing otherwise."""
    typed = words(query)
    if not typed:
        return []
    patterns = [re.compile(rf"\b{re.escape(word)}\w*", re.IGNORECASE) for word in typed]
    found = [item for item in items if all(p.search(plain(text(item))) for p in patterns)]
    if not meaning_first:
        return found
    meaning = [item for item in found
               if all(p.search(re.split(r"[.;]", plain(text(item)), maxsplit=1)[0]) for p in patterns)]
    return meaning or found
