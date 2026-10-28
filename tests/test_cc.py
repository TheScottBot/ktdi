"""Conservative calls (/cc, !cc): our own quote book for the gag, apart from the real quotes (ktdi.features.cc)."""

from ktdi.features import cc, quotes
from tests.fakes import Ctx, Interaction, Message, User, run

SCOTT, DAVE, PAT = User(1, "scott"), User(2, "dave"), User(3, "pat")
MOD = User(4, "mod", mod=True)


def typed(author, args="", **kwargs):
    ctx = Ctx(author, slash=False, **kwargs)
    run(cc.cc_prefix.callback(ctx, args=args))
    return ctx.last


def slash(user, **options):
    interaction = Interaction(user)
    run(cc.cc_slash.callback(interaction, **options))
    return interaction.sent[-1]


def test_it_starts_empty():
    assert "Nothing yet" in typed(SCOTT).content and "Nothing yet" in slash(SCOTT).content


def test_adding_and_recalling_one():
    added = typed(SCOTT, "add One of the alphabet people -- Uncle Clive, lowering his voice")
    assert added.content == "🧓 Added #1."
    recalled = slash(DAVE).embed.description
    assert recalled.startswith(cc.INTRO + "\n## “One of the alphabet people”")
    assert "*— Uncle Clive, lowering his voice*" in recalled and "<@" not in recalled  # Nobody's named


def test_a_reply_saves_the_words_but_not_who_wrote_them():
    tarps = Message(9001, DAVE, "People haven't been taking their tarps in")
    saved = typed(SCOTT, reply_to=tarps)
    assert "“People haven't been taking their tarps in”" in saved.embed.description and "<@" not in saved.embed.description
    assert quotes.get_quote(111, 1, table=cc.TABLE).user_id == quotes.ANONYMOUS


def test_slash_add_number_search_and_delete():
    slash(SCOTT, add="Doesn't take their tarps in", who="Gerald from the golf club")
    slash(SCOTT, add="One of the letters")
    assert "“One of the letters”" in slash(DAVE, number=2).embed.description
    found = slash(DAVE, search="tarps").embed.description
    assert "#1" in found and "letters" not in found
    assert "Only whoever added" in slash(PAT, delete=1).content
    assert slash(MOD, delete=1).content == "🗑️ Deleted #1."
    assert "There's no #1" in slash(DAVE, number=1).content


def test_typed_ways_in():
    typed(SCOTT, "add Very theatrical, if you know what I mean")
    assert "“Very theatrical" in typed(DAVE, "1").embed.description
    assert "#1" in typed(DAVE, "last").embed.description and "#1" in typed(DAVE, "search theatrical").embed.description
    assert "Try `!cc`" in typed(DAVE, "what is this").content
    assert typed(SCOTT, "delete 1").content == "🗑️ Deleted #1."


def test_its_own_book_apart_from_the_real_quotes():
    typed(SCOTT, "add The rainbow brigade")
    quotes.add_quote(111, DAVE.id, "I cast fireball on myself", None, SCOTT.id)
    assert quotes.get_quote(111, 1).text == "I cast fireball on myself"  # Quote #1 is still the real one
    assert quotes.get_quote(111, 1, table=cc.TABLE).text == "The rainbow brigade"
    assert quotes.random_quote(111).text == "I cast fireball on myself"
