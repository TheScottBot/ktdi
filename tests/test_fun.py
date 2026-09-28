"""Spray, rap sheets, blame and bribe (ktdi.features.fun)."""

import types

from ktdi.features import fun
from tests.fakes import Channel, Ctx, Guild, User, run

SCOTT, DAVE = User(1, "scott"), User(2, "dave")


def test_spray_counts_on_the_rap_sheet():
    ctx = Ctx(SCOTT)
    run(fun.spray.callback(ctx, DAVE))
    run(fun.spray.callback(ctx, DAVE))
    run(fun.spray.callback(ctx))  # no target: GIF only, not counted
    assert ctx.sent[0].content == f"<@2> {fun.SPRAY_GIF_URL}"
    assert fun.get_spray_count(111, DAVE.id) == 2
    run(fun.rapsheet.callback(ctx, DAVE))
    assert "Sprayed 2 times." in ctx.last.content


def test_clean_record():
    ctx = Ctx(SCOTT)
    run(fun.rapsheet.callback(ctx, DAVE))
    assert "clean record" in ctx.last.content


def test_spray_reaction(bot):
    channel = bot.add_channel(Channel(700, Guild()))
    payload = types.SimpleNamespace(emoji="💦", user_id=SCOTT.id, channel_id=700, guild_id=111,
                                    message_author_id=DAVE.id, member=SCOTT)
    run(fun.spray_reaction(payload))
    assert channel.sent[-1].content == f"<@2> {fun.SPRAY_GIF_URL}"
    assert fun.get_spray_count(111, DAVE.id) == 1
    # Other emojis, and the bot's own reactions, do nothing.
    run(fun.spray_reaction(types.SimpleNamespace(**{**payload.__dict__, "emoji": "😂"})))
    run(fun.spray_reaction(types.SimpleNamespace(**{**payload.__dict__, "user_id": bot.user.id})))
    assert len(channel.sent) == 1


def test_blame_then_bribe_and_counter_bribe():
    channel = Channel(500, Guild())
    fun.recent_speakers[500].append(DAVE.id)
    run(fun.blame.callback(Ctx(SCOTT, channel=channel), reason="server died"))
    assert fun.last_blame[500] == (SCOTT.id, DAVE.id)

    ctx = Ctx(User(3, "pat"), channel=channel)
    run(fun.bribe.callback(ctx, 100))
    assert "not the one being blamed" in ctx.last.content and ctx.last.private

    ctx = Ctx(DAVE, channel=channel)
    run(fun.bribe.callback(ctx, 500))
    assert "$500" in ctx.last.content
    assert fun.last_blame[500] == (DAVE.id, SCOTT.id)  # flipped, so Scott can counter-bribe

    run(fun.bribe.callback(Ctx(SCOTT, channel=channel), 2000))
    assert fun.get_bribe_stats(111, SCOTT.id) == (1, 2000)
    assert fun.get_top_briber(111) == SCOTT.id


def test_bribe_with_nobody_blamed():
    ctx = Ctx(DAVE)
    run(fun.bribe.callback(ctx, 10))
    assert "Nobody's been blamed" in ctx.last.content
