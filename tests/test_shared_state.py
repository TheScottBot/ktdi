"""Shared state: which servers see each other's quotes, sprays, bribes and campaigns (ktdi.db.scope)."""

import pytest
from discord.ext import commands

from ktdi import db
from ktdi.features import campaigns, fun, quotes, settings
from tests.fakes import Ctx, Guild, User, run

A, B, C = Guild(111, "Hangout"), Guild(222, "Other"), Guild(333, "Private")
SCOTT, DAVE, ADMIN = User(1, "scott"), User(2, "dave"), User(9, "admin", admin=True)


def texts(guild):
    return [q.text for q in quotes.recent_quotes(guild.id, 10)]


def set_shared(guild, value):
    run(settings.settings_shared_state.callback(Ctx(ADMIN, guild), value))


def test_scope_clause():
    assert db.scope(111) == ("1 = 1", [])
    db.set_shared(333, False)
    assert db.scope(111) == ("guild_id NOT IN (?)", [333])
    assert db.scope(333) == ("guild_id = ?", [333])


def test_shared_by_default_then_isolated_then_back(bot):
    bot.guilds = [A, B, C]
    quotes.add_quote(A.id, DAVE.id, "from A", None, SCOTT.id)
    quotes.add_quote(B.id, DAVE.id, "from B", None, SCOTT.id)
    fun.record_spray(A.id, DAVE.id)
    fun.record_spray(B.id, DAVE.id)
    assert texts(A) == ["from B", "from A"]
    assert fun.get_spray_count(A.id, DAVE.id) == 2

    set_shared(C, False)
    c_quote = quotes.add_quote(C.id, SCOTT.id, "from C", None, SCOTT.id)
    fun.record_spray(C.id, DAVE.id)
    assert texts(C) == ["from C"]
    assert "from C" not in texts(A)
    assert fun.get_spray_count(A.id, DAVE.id) == 2 and fun.get_spray_count(C.id, DAVE.id) == 1
    assert quotes.get_quote(A.id, c_quote) is None
    quotes.delete_quote(A.id, c_quote)  # can't touch what it can't see
    assert quotes.get_quote(C.id, c_quote) is not None

    set_shared(C, True)  # nothing lost
    assert texts(C) == ["from C", "from B", "from A"]
    assert fun.get_spray_count(C.id, DAVE.id) == 3


def test_campaigns_across_servers(bot):
    ddb = "https://www.dndbeyond.com/campaigns/"
    run(campaigns.campaign_add.callback(Ctx(SCOTT, A), "Monday game", ddb + "1", None))
    ctx = Ctx(SCOTT, B)
    run(campaigns.campaign_add.callback(ctx, "monday GAME", ddb + "2", None))
    assert "already a campaign" in ctx.last.content  # aliases are unique across shared servers

    set_shared(C, False)
    run(campaigns.campaign_add.callback(Ctx(SCOTT, C), "Monday game", ddb + "3", None))  # fine while isolated
    set_shared(C, True)
    assert campaigns.get_campaign(A.id, "Monday game").guild_id == A.id  # each server's own first
    assert campaigns.get_campaign(C.id, "Monday game").guild_id == C.id

    # Edit A's campaign from B: the change lands on A's row.
    run(campaigns.campaign_edit.callback(Ctx(SCOTT, A), "Monday game", rename="Monday night"))
    run(campaigns.campaign_edit.callback(Ctx(SCOTT, B), "Monday night", vtt="https://app.roll20.net/x"))
    assert campaigns.get_campaign_exact(A.id, "Monday night").vtt_url == "https://app.roll20.net/x"


def test_settings_needs_manage_server(bot):
    bot.guilds = [A, B, C]
    check = settings.settings_shared_state.checks[0]
    with pytest.raises(commands.CheckFailure, match="Manage Server"):
        run(check(Ctx(DAVE, C)))
    ctx = Ctx(ADMIN, C)
    run(settings.settings_shared_state.callback(ctx, False))
    assert "🔒 **Off**" in ctx.last.content
    run(settings.settings_shared_state.callback(ctx, False))
    assert "already off" in ctx.last.content


def test_whospray_user_setting(bot):
    check = settings.settings_whospray_user.checks[0]
    with pytest.raises(commands.CheckFailure, match="Manage Server"):
        run(check(Ctx(DAVE, A)))
    ctx = Ctx(ADMIN, A)
    run(settings.settings_whospray_user.callback(ctx, DAVE))
    assert "will now ask <@2>" in ctx.last.content and db.whospray_user(A.id) == DAVE.id
    run(settings.settings_show.callback(ctx))
    assert "Who /whospray asks: <@2>" in ctx.last.text
    run(settings.settings_whospray_user.callback(ctx))
    assert db.whospray_user(A.id) is None and "won't ask anyone" in ctx.last.content


def test_settings_show_counts_other_servers(bot):
    bot.guilds = [A, B, C]
    ctx = Ctx(SCOTT, A)
    run(settings.settings_show.callback(ctx))
    assert "2 other servers that have it on" in ctx.last.text
    db.set_shared(C.id, False)
    run(settings.settings_show.callback(ctx))
    assert "1 other server that has it on" in ctx.last.text


def test_rap_sheet_crown_wording():
    fun.record_bribe(A.id, DAVE.id, 500)
    ctx = Ctx(SCOTT, A)
    run(fun.rapsheet.callback(ctx, DAVE))
    assert "across the shared servers" in ctx.last.content
    db.set_shared(A.id, False)
    run(fun.rapsheet.callback(ctx, DAVE))
    assert "in the server" in ctx.last.content
