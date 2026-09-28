"""Quotes: every way in, anonymous quotes, dissociate/claim, lists and permissions (ktdi.features.quotes)."""

from ktdi.features import quotes as q
from tests.fakes import Ctx, Interaction, Message, User, run

SCOTT, DAVE, PAT = User(1, "scott"), User(2, "dave"), User(3, "pat")
MOD = User(4, "mod", mod=True)


def prefix_quote(author, args="", **kwargs):
    ctx = Ctx(author, slash=False, **kwargs)
    run(q.quote_prefix.callback(ctx, args=args))
    return ctx.last


def test_typed_quote_with_context():
    reply = prefix_quote(SCOTT, f"<@{DAVE.id}> I cast fireball on myself -- we were all in the blast radius",
                         mentions=[DAVE])
    assert reply.content == "📌 Saved quote #1."
    assert "“I cast fireball on myself”" in reply.embed.description
    assert "*we were all in the blast radius*" in reply.embed.description


def test_reply_saves_the_message_once():
    message = Message(9001, DAVE, "Is the mimic in the room with us right now?")
    reply = prefix_quote(SCOTT, reply_to=message)
    assert "<@2>" in reply.embed.description and "Original message" in reply.embed.description
    again = prefix_quote(SCOTT, reply_to=message)
    assert again.content == "That's already saved as quote #1."


def test_reply_credits_someone_else_and_can_reword():
    relay = Message(9002, SCOTT, "pat just said Linux is fine")
    reply = prefix_quote(DAVE, f"<@{PAT.id}> I'd rather eat a d20 than use Linux", reply_to=relay, mentions=[PAT])
    assert "“I'd rather eat a d20 than use Linux”" in reply.embed.description and "<@3>" in reply.embed.description


def test_typed_quote_needs_a_person():
    assert "Who said it?" in prefix_quote(SCOTT, "who said this").content


def test_slash_add_without_user_is_anonymous():
    interaction = Interaction(SCOTT)
    run(q.quote_slash_add.callback(interaction, text="anon quote"))
    assert interaction.last.content == "📌 Saved anonymous quote #1."
    assert "*Anonymous*" in interaction.last.embed.description


def test_prefix_anon_variants():
    run(q.quote_prefix_add.callback(Ctx(SCOTT, slash=False), None, text="anon the goblin did it"))
    run(q.quote_prefix_anon.callback(Ctx(SCOTT, slash=False), text="I'm not saying it was aliens -- rations"))
    anonymous = [row.text for row in q.recent_quotes(111, 10)]
    assert anonymous == ["I'm not saying it was aliens", "the goblin did it"]


def test_anonymous_reply_drops_the_message_link():
    message = Message(9010, DAVE, "I have 3 HP and a dream")
    run(q.quote_prefix_anon.callback(Ctx(SCOTT, slash=False, reply_to=message), text=""))
    saved = q.get_quote(111, 1)
    assert saved.user_id == q.ANONYMOUS and saved.message_id is None and saved.channel_id is None


def test_right_click_form():
    interaction = Interaction(SCOTT)
    run(q.save_quote_menu.callback(interaction, Message(9003, SCOTT, "pat says: arch btw")))
    form = interaction.modal
    assert form.quote_text.default == "pat says: arch btw"
    form.quote_text._value, form.said_by._values, form.context._value = "arch btw", [PAT], "while complaining"
    submit = Interaction(SCOTT)
    run(form.on_submit(submit))
    assert "<@3>" in submit.last.embed.description and "*while complaining*" in submit.last.embed.description


def test_right_click_form_cleared_picker_is_anonymous():
    interaction = Interaction(SCOTT)
    run(q.save_quote_menu.callback(interaction, Message(9004, DAVE, "roll for vibes")))
    form = interaction.modal
    form.quote_text._value, form.said_by._values, form.context._value = "roll for vibes", [], ""
    submit = Interaction(SCOTT)
    run(form.on_submit(submit))
    assert "Saved anonymous quote" in submit.last.content


def test_limits():
    assert "a bit long for a quote" in prefix_quote(SCOTT, f"<@{DAVE.id}> " + "blah " * 300, mentions=[DAVE]).content
    empty = Interaction(SCOTT)
    run(q.save_quote_menu.callback(empty, Message(9005, DAVE, "")))
    empty.modal.quote_text._value, empty.modal.said_by._values = "", [DAVE]
    submit = Interaction(SCOTT)
    run(empty.modal.on_submit(submit))
    assert "has no text" in submit.last.content and submit.last.private


def test_random_show_last_and_search():
    for text, who in [("first", DAVE), ("Linux is fine actually", PAT), ("arch btw 100%", PAT)]:
        q.add_quote(111, who.id, text, None, SCOTT.id)
    interaction = Interaction(SCOTT)
    run(q.quote_slash_random.callback(interaction, PAT))
    assert "<@3>" in interaction.last.embed.description
    run(q.quote_slash_show.callback(interaction, 99))
    assert interaction.last.content == "There's no quote #99." and interaction.last.private
    run(q.quote_slash_last.callback(interaction, 2))
    assert interaction.last.embed.title == "🗒️ Last 2 quotes"
    assert interaction.last.embed.description.startswith("`#3`")
    run(q.quote_slash_search.callback(interaction, "100%"))
    assert "#3" in interaction.last.embed.description and "#1" not in interaction.last.embed.description
    run(q.quote_slash_search.callback(interaction, "%"))  # a literal %, not a wildcard
    assert "#3" in interaction.last.embed.description and "#2" not in interaction.last.embed.description


def test_delete_permissions():
    q.add_quote(111, DAVE.id, "mine", None, SCOTT.id)
    interaction = Interaction(PAT)
    run(q.quote_slash_delete.callback(interaction, 1))
    assert "Only whoever saved" in interaction.last.content
    run(q.quote_slash_delete.callback(Interaction(DAVE), 1))  # the person quoted may
    assert q.get_quote(111, 1) is None
    q.add_quote(111, DAVE.id, "another", None, SCOTT.id)
    run(q.quote_slash_delete.callback(Interaction(MOD), 2))  # so may a mod
    assert q.get_quote(111, 2) is None


def test_dissociate_then_claim_back():
    q.add_quote(111, PAT.id, "I would rather eat a d20", None, DAVE.id, channel_id=500, message_id=9002)
    refused = Interaction(User(5, "rando"))
    run(q.quote_slash_dissociate.callback(refused, 1))
    assert "Only the person quoted" in refused.last.content
    run(q.quote_slash_dissociate.callback(Interaction(PAT), 1))
    quote = q.get_quote(111, 1)
    assert quote.user_id == q.ANONYMOUS and quote.message_id is None  # the link would give it away

    interaction = Interaction(DAVE)
    run(q.quote_slash_claim.callback(interaction, 1))
    assert "claimed quote #1" in interaction.last.content
    run(q.quote_slash_claim.callback(Interaction(PAT), 1))  # no longer anonymous
    assert q.get_quote(111, 1).user_id == DAVE.id


def test_no_pings():
    interaction = Interaction(SCOTT)
    run(q.quote_slash_add.callback(interaction, text="@everyone look", user=DAVE))
    assert interaction.last.allowed_mentions.everyone is False and interaction.last.allowed_mentions.users is False
