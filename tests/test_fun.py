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


def test_whospray_asks_the_chosen_person_and_only_pings_them():
    from ktdi import db
    db.set_whospray_user(111, DAVE.id)
    ctx = Ctx(SCOTT)
    run(fun.whospray.callback(ctx))
    reply = ctx.last
    assert reply.content.startswith("💦 <@2>")
    assert any(line.format(user="<@2>") in reply.content for line in fun.WHOSPRAY_LINES)
    assert [u.id for u in reply.allowed_mentions.users] == [DAVE.id]
    assert reply.allowed_mentions.everyone is False and reply.allowed_mentions.roles is False


def test_whospray_has_no_options():
    # Only ever asks the person chosen in /settings whospray_user.
    assert fun.whospray.app_command.parameters == []
    assert fun.whospray.clean_params == {}


def test_whospray_with_no_don():
    ctx = Ctx(SCOTT)
    run(fun.whospray.callback(ctx))
    assert "There's no Don on this server yet" in ctx.last.content and ctx.last.private
    assert "user:" not in ctx.last.content


def test_tdoi_sprays_yourself_and_counts_twice():
    from ktdi import db
    db.set_whospray_user(111, DAVE.id)  # Dave is the Don
    ctx = Ctx(SCOTT)
    run(fun.tdoi.callback(ctx))
    run(fun.tdoi.callback(ctx))
    reply = ctx.last
    assert reply.content.startswith("🤌 The Don ordered it. <@1> sprays themselves.")
    assert fun.SPRAY_GIF_URL in reply.content and "That's 2 times the Don has made them do it." in reply.content
    assert reply.allowed_mentions.users is False and reply.allowed_mentions.everyone is False  # no pings
    assert fun.get_spray_count(111, SCOTT.id) == 2  # a normal spray...
    assert fun.get_don_order_count(111, SCOTT.id) == 2  # ...and a Don order
    run(fun.rapsheet.callback(ctx, SCOTT))
    assert "Sprayed 2 times." in ctx.last.content
    assert "🤌 Sprayed themselves on the Don's orders 2 times." in ctx.last.content


def test_tdoi_with_no_don():
    ctx = Ctx(SCOTT)
    run(fun.tdoi.callback(ctx))
    assert "There's no Don" in ctx.last.content and ctx.last.private
    assert fun.get_spray_count(111, SCOTT.id) == 0


def test_rap_sheet_without_don_orders_has_no_don_line():
    fun.record_spray(111, DAVE.id)
    ctx = Ctx(SCOTT)
    run(fun.rapsheet.callback(ctx, DAVE))
    assert "Don" not in ctx.last.content


def test_whospray_setting_is_per_server():
    from ktdi import db
    db.set_whospray_user(111, DAVE.id)
    assert db.whospray_user(222) is None
    assert db.is_shared(111)  # setting it didn't change shared state


def test_expunge_removes_a_spray_and_counts_as_a_bribe():
    for _ in range(3):
        fun.record_spray(111, DAVE.id)
    ctx = Ctx(DAVE)
    run(fun.expunge.callback(ctx, 500))
    reply = ctx.last
    assert any(line.format(user="<@2>", amount="$500") in reply.content for line in fun.EXPUNGE_LINES)
    assert "2 sprays left on their record." in reply.content
    assert reply.allowed_mentions.users is False  # no pings
    assert fun.get_spray_count(111, DAVE.id) == 2
    assert fun.get_bribe_stats(111, DAVE.id) == (1, 500)  # it's a bribe, so it counts toward the crown
    assert fun.get_top_briber(111) == DAVE.id
    run(fun.rapsheet.callback(ctx, DAVE))
    sheet = ctx.last.content
    assert "Sprayed 2 times." in sheet and "🧽 Paid to have 1 spray expunged." in sheet
    assert "Bribed the committee 1 time ($500 total)." in sheet


def test_expunge_needs_a_spray_to_remove():
    ctx = Ctx(DAVE)
    run(fun.expunge.callback(ctx, 100))
    assert "no sprays on it" in ctx.last.content and ctx.last.private
    assert fun.get_bribe_stats(111, DAVE.id) == (0, 0)  # nothing charged


def test_expunging_everything_then_being_sprayed_again():
    fun.record_spray(111, DAVE.id)
    run(fun.expunge.callback(Ctx(DAVE), 10))
    assert fun.get_spray_count(111, DAVE.id) == 0
    run(fun.expunge.callback(Ctx(DAVE), 10))  # nothing left to expunge
    assert fun.get_expunge_count(111, DAVE.id) == 1
    fun.record_spray(111, DAVE.id)
    assert fun.get_spray_count(111, DAVE.id) == 1


def test_expunge_leaves_the_don_count_alone():
    from ktdi import db
    db.set_whospray_user(111, SCOTT.id)
    run(fun.tdoi.callback(Ctx(DAVE)))
    run(fun.expunge.callback(Ctx(DAVE), 50))
    assert fun.get_spray_count(111, DAVE.id) == 0
    assert fun.get_don_order_count(111, DAVE.id) == 1  # the Don remembers


def test_bail_removes_someone_elses_spray_and_counts_as_the_payers_bribe():
    fun.record_spray(111, DAVE.id)
    fun.record_spray(111, DAVE.id)
    ctx = Ctx(SCOTT)
    run(fun.bail.callback(ctx, DAVE, 300))
    reply = ctx.last
    expected = [line.format(payer="<@1>", target="<@2>", amount="$300") for line in fun.BAIL_LINES]
    assert any(line in reply.content for line in expected)
    assert "1 spray left on their record." in reply.content and reply.allowed_mentions.users is False
    assert fun.get_spray_count(111, DAVE.id) == 1
    assert fun.get_bribe_stats(111, SCOTT.id) == (1, 300)  # the payer's bribe...
    assert fun.get_bribe_stats(111, DAVE.id) == (0, 0)  # ...not the person bailed out
    run(fun.rapsheet.callback(ctx, DAVE))
    assert "🔓 Bailed out of 1 spray by others." in ctx.last.content
    run(fun.rapsheet.callback(ctx, SCOTT))
    assert "🤝 Bailed others out 1 time." in ctx.last.content


def test_bail_refusals():
    ctx = Ctx(SCOTT)
    run(fun.bail.callback(ctx, SCOTT, 10))
    assert "can't bail yourself" in ctx.last.content and ctx.last.private
    run(fun.bail.callback(ctx, DAVE, 10))
    assert "no sprays on their record" in ctx.last.content and ctx.last.private
    assert fun.get_bribe_stats(111, SCOTT.id) == (0, 0)  # nothing charged


def test_expunge_and_bail_together():
    for _ in range(3):
        fun.record_spray(111, DAVE.id)
    run(fun.expunge.callback(Ctx(DAVE), 10))
    run(fun.bail.callback(Ctx(SCOTT), DAVE, 10))
    run(fun.bail.callback(Ctx(User(3, "pat")), DAVE, 10))
    assert fun.get_spray_count(111, DAVE.id) == 0
    ctx = Ctx(SCOTT)
    run(fun.bail.callback(ctx, DAVE, 10))  # nothing left
    assert "no sprays" in ctx.last.content


def test_fully_bailed_out_still_shows_a_rap_sheet():
    fun.record_spray(111, DAVE.id)
    run(fun.bail.callback(Ctx(SCOTT), DAVE, 10))
    ctx = Ctx(SCOTT)
    run(fun.rapsheet.callback(ctx, DAVE))
    assert "clean record" not in ctx.last.content
    assert "🔓 Bailed out of 1 spray by others." in ctx.last.content and "Sprayed" not in ctx.last.content


def test_bribe_with_nobody_blamed():
    ctx = Ctx(DAVE)
    run(fun.bribe.callback(ctx, 10))
    assert "Nobody's been blamed" in ctx.last.content
