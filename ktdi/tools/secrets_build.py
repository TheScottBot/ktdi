"""Build /secrets's passages from The Boke of Secretes of Albertus Magnus (English, 1560: herbs, stones and beasts,
then The Meruayles of the World), as transcribed by hand for the Text Creation Partnership (EEBO-TCP: public domain,
CC0): python -m ktdi.tools.secrets_build

It isn't really by Albertus (a medieval compilation that borrowed his name), and it's a book of magic: lay a
lodestone under your wife's head to learn if she's faithful, carry marigold and a wolf's tooth so nobody can speak
against you, make a lamp that gives everyone in the room a dog's face. The book was read once, and its harmless
magic kept in ktdi/lib/secrets_curation.json (see tools/tcp.py for how), but nothing anyone could make and be hurt
by (arsenic, quicksilver, henbane, setting yourself alight), no cures, nothing sexual, and nothing cruel to animals.
Writes ktdi/lib/secrets.json, each secret with its page in the scan of the printed book on archive.org.

To add one, read it in the book, then add its paragraph number (and if need be, its section) to the curation.
"""

from ktdi.tools import tcp

BOOKS = {"secrets": {"tcp": "A15531",
                     "scan": "bim_early-english-books-1475-1640_the-boke-of-secretes-of-_albertus-magnus_1560"}}
CURATION = tcp.gutenberg.curation_file("secrets")


def main() -> None:
    tcp.build("secrets", BOOKS)


if __name__ == "__main__":
    main()
