"""Links into old books at the exact spot (ktdi.lib.links), and finding each /deadword's page in Mackay's scan
(ktdi.tools.deadword_pages)."""

from ktdi.lib import links
from ktdi.tools import deadword_pages as pages


# --- Gutenberg text fragments ---
def test_fragment_text_takes_the_first_run_of_plain_words():
    assert links.fragment_text("It helps the quinsy wonderfully, and is good for the cough.", words=6) == \
        "It helps the quinsy wonderfully, and"
    assert links.fragment_text("…the decoction drunk eases the gout.") == "the decoction drunk eases the gout."
    assert links.fragment_text("A shabby ill-dressed fellow.") == "A shabby ill-dressed fellow."  # single hyphen
    assert links.fragment_text("He said--no, he wasn't there, but we all went home together.") == \
        "there, but we all went home together."  # Skips past the dash and the apostrophe to a run long enough


def test_fragment_text_needs_enough_words_to_find_it_by():
    assert links.fragment_text("I'd say so.") == ""  # Nothing long enough: no fragment
    assert links.fragment_text("BENE. Good. CANT.", least=2) == "BENE. Good. CANT."


def test_gutenberg_links():
    base = "https://www.gutenberg.org/cache/epub/5402/pg5402-images.html"
    assert links.gutenberg(5402) == base
    assert links.gutenberg(5402, "I'd say so.") == base  # No fragment: the book, from the top
    assert links.gutenberg(5402, "Drunk, and very much so, at the inn.") == (
        base + "#:~:text=Drunk%2C%20and%20very%20much%20so%2C%20at%20the%20inn.")  # "," escaped
    assert links.gutenberg(5402, "A shabby ill-dressed fellow.").endswith("ill%2Ddressed%20fellow.")  # and "-"


def test_archive_links():
    assert links.archive_page("abc", None) == "https://archive.org/details/abc"
    assert links.archive_page("abc", 41, "Bell-penny") == "https://archive.org/details/abc/page/n41/mode/2up?q=Bell-penny"


# --- Finding a dead word's page ---
def djvu(*pages_of_lines: list[str]) -> str:
    """A tiny _djvu.xml: pages of lines of words."""
    def line(text):
        return "<LINE>" + "".join(f"<WORD coords='0'>{word}</WORD>" for word in text.split()) + "</LINE>"
    return "".join("<OBJECT data='x'>" + "".join(line(text) for text in lines) + "</OBJECT>" for lines in pages_of_lines)


BOOK = djvu(
    ["LOST BEAUTIES", "Introduction, which mentions Bever in passing."],
    ["Abear, to tolerate.", "Acold, very cold."],
    ["Bxll-penny, money for one's funeral.", "Bever, a drink between meals.", "Zzzz, OCR noise out of order.",
     "Bicker, a drinking cup."],
    ["Blae, livid."],
    ["Ynling, keeping Christmas."],
    ["BOOKS PUBLISHED BY CHATTO", "Bever, an advert."],
)


def test_signposts_keep_the_dictionary_in_alphabetical_order():
    posts = pages.signposts(pages.line_starts(BOOK))
    # The mangled "Bxll-penny" and the "Zzzz" noise are out of order, so they drop out; the introduction and the
    # adverts are outside the dictionary (Abear to Ynling).
    assert posts == [("abear", 1), ("acold", 1), ("bever", 2), ("bicker", 2), ("blae", 3), ("ynling", 4)]


def test_page_of_a_word():
    posts = pages.signposts(pages.line_starts(BOOK))
    assert pages.page_of("Bever", posts) == 2  # Its own headword
    # OCR'd as "Bxll-penny", so it falls just after Acold: page 1, whose link shows page 2 beside it.
    assert pages.page_of("Bell-penny", posts) == 1


def test_add_pages_checks_the_text():
    posts, texts = pages.signposts(pages.line_starts(BOOK)), pages.page_texts(BOOK)
    words = [{"word": "Acold"}, {"word": "Bell-penny"}, {"word": "Bever"}, {"word": "Blae"}]
    # All four are on the pages their links show: "Bxll-penny" on page 2 is one OCR slip from "Bell-penny".
    assert pages.add_pages(words, posts, texts) == 4
    assert [w["page"] for w in words] == [1, 1, 2, 3]
    assert pages.add_pages([{"word": "Zebra"}], posts, texts) == 0  # Never in the text: placed, but not sure of


# --- Finding a weather saying's page ---
def test_weather_sayings_are_found_by_their_word_pairs():
    from ktdi.tools import weather_lore_pages as lore
    book = djvu(["Contents and so on"], ["A winter fog / Will freeze a dog.", "Rain before seven, fine by eleven."],
                ["A second fog page with a dog", "Red sky at night, shepherd's delight."])
    pages_text = lore.page_words(book)
    sayings = [{"text": "A winter fog / Will freeze a dog."}, {"text": "Red sky at night, / Shepherd's delight."}]
    assert lore.add_pages(sayings, pages_text) == 2
    assert [s["page"] for s in sayings] == [1, 2]
    assert sayings[0]["highlight"] == "winter"  # Its rarest plain word (ties: the longest)
