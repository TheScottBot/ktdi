"""Build /bestiary's passages from Edward Topsell's The Historie of Foure-footed Beastes (1607) and The Historie of
Serpents (1608), as transcribed by hand for the Text Creation Partnership (EEBO-TCP: public domain, CC0):
python -m ktdi.tools.bestiary_build

Topsell gathered everything ever said about every animal (mostly from Gesner, who'd gathered it from Pliny, Aelian
and everyone since), believed nearly all of it, and added the unicorn, the lamia, the mantichora and the gorgon as
beasts like any other. His chapters are long (the horse runs to a book of its own), so the kept text is single
paragraphs, picked by hand: ktdi/lib/bestiary_curation.json lists, for each beast, a modern name to look it up by
and the paragraphs kept (see tools/tcp.py for how). Racist passages about real peoples, sex, cruelty to animals and
remedies anyone might try were left out. Writes ktdi/lib/bestiary.json, each passage with its page in the scan of the
printed book on archive.org.

To add a paragraph, read it in the book, then add its number (and if need be, the beast) to the curation.
"""

from ktdi.tools import tcp

BOOKS = {
    "beasts": {"tcp": "A13820",
               "scan": "bim_early-english-books-1475-1640_the-historie-of-foure-fo_topsell-edward_1607"},
    "serpents": {"tcp": "A13821",
                 "scan": "bim_early-english-books-1475-1640_the-historie-of-serpents_topsell-edward_1608"},
}
CURATION = tcp.gutenberg.curation_file("bestiary")


def main() -> None:
    tcp.build("bestiary", BOOKS)


if __name__ == "__main__":
    main()
