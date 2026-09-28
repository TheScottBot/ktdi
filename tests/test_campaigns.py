"""Campaigns: adding, links, show/list, editing, permissions, autocomplete (ktdi.features.campaigns)."""

import types

import pytest

from ktdi.features import campaigns as c
from tests.fakes import Ctx, User, run

SCOTT, DAVE, MOD = User(1, "scott"), User(2, "dave"), User(4, "mod", mod=True)
DDB = "https://www.dndbeyond.com/campaigns/1234567"
ROLL20 = "https://app.roll20.net/join/9999/abcd"
OWLBEAR = "https://www.owlbear.rodeo/room/xyz"


def add(author, alias, first=None, second=None):
    ctx = Ctx(author)
    run(c.campaign_add.callback(ctx, alias, first, second))
    return ctx.last


def test_add_sorts_links_and_names_buttons():
    reply = add(SCOTT, "Wednesday  game ", ROLL20, DDB)  # links the "wrong" way round, stray spaces
    assert reply.content == "🎲 Campaign added."
    assert reply.embed.title == "🎲 Wednesday game"
    assert [(b.label, b.url) for b in reply.view.children] == [("D&D Beyond", DDB), ("Roll20", ROLL20)]


@pytest.mark.parametrize("url, label", [
    ("https://foundry.example.com/join", "VTT"), (OWLBEAR, "Owlbear Rodeo"), ("https://x.forge-vtt.com/game", "The Forge"),
])
def test_vtt_labels(url, label):
    assert c.vtt_label(url) == label


@pytest.mark.parametrize("args, message", [
    (("list", DDB), "is a command name"),
    (("Friday", None, None), "at least one link"),
    (("Friday", "not a link"), "doesn't look like a link"),
    (("Friday", ROLL20, OWLBEAR), "one D&D Beyond campaign link and one VTT link"),
    (("https://x.com", DDB), "The alias goes first"),
])
def test_add_problems(args, message):
    reply = add(SCOTT, *args)
    assert message in reply.content and reply.private


def test_duplicate_alias_any_case():
    add(SCOTT, "Monday game", DDB)
    assert "already a campaign" in add(SCOTT, "monday GAME", DDB).content


def test_links_in_angle_brackets():
    add(DAVE, "Oneshots", f"<{OWLBEAR}>")
    assert c.get_campaign(111, "oneshots").vtt_url == OWLBEAR


def test_show_list_and_prefix_shorthand():
    add(SCOTT, "Monday game", DDB, ROLL20)
    add(DAVE, "The cursed one", "https://foundry.example.com/join")
    ctx = Ctx(DAVE)
    run(c.campaign_show.callback(ctx, alias="MONDAY game"))
    assert ctx.last.embed.title == "🎲 Monday game"
    run(c.campaign_list.callback(ctx))
    assert "**Monday game**" in ctx.last.embed.description and "**The cursed one**" in ctx.last.embed.description
    run(c.campaign_group.callback(ctx, alias="the cursed one"))  # !campaign the cursed one
    assert ctx.last.embed.title == "🎲 The cursed one"
    run(c.campaign_show.callback(ctx, alias="Friday"))
    assert "There's no campaign" in ctx.last.content


def edit(author, alias="Monday game", **changes):
    ctx = Ctx(author)
    run(c.campaign_edit.callback(ctx, alias, **changes))
    return ctx.last


def test_edit_permissions_and_rules():
    add(SCOTT, "Monday game", DDB, ROLL20)
    add(SCOTT, "Wednesday game", DDB.replace("1234567", "7"))
    assert "Only whoever added" in edit(DAVE, vtt=OWLBEAR).content
    assert "Campaign updated" in edit(SCOTT, vtt=OWLBEAR, rename="Monday night").content
    assert c.get_campaign(111, "Monday night").vtt_url == OWLBEAR
    assert "Campaign updated" in edit(MOD, alias="Monday night", vtt="none").content
    assert c.get_campaign(111, "Monday night").vtt_url is None
    assert "needs at least one link" in edit(MOD, alias="Monday night", dndbeyond="none").content
    assert "isn't a D&D Beyond link" in edit(SCOTT, alias="Monday night", dndbeyond=ROLL20).content
    assert "already a campaign" in edit(SCOTT, alias="Monday night", rename="wednesday game").content


def test_remove_permissions():
    add(DAVE, "Oneshots", OWLBEAR)
    ctx = Ctx(SCOTT)
    run(c.campaign_remove.callback(ctx, alias="Oneshots"))
    assert "Only whoever added" in ctx.last.content
    run(c.campaign_remove.callback(Ctx(DAVE), alias="oneshots"))
    assert c.get_campaign(111, "Oneshots") is None


def test_alias_autocomplete():
    for alias in ("Monday game", "Wednesday game", "The cursed one"):
        add(SCOTT, alias, DDB.replace("1234567", str(len(alias))))
    interaction = types.SimpleNamespace(guild_id=111)
    names = lambda typed: [choice.name for choice in run(c.campaign_alias_autocomplete(interaction, typed))]
    assert names("") == ["Monday game", "The cursed one", "Wednesday game"]
    assert names("game") == ["Monday game", "Wednesday game"]
    assert names("CURSE") == ["The cursed one"]
