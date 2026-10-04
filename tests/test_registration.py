"""Loading every feature onto a real bot registers the expected commands, and /help stays within Discord's limits."""

import asyncio

import discord
import pytest
from discord.ext import commands

from ktdi.bot import KTDIBot, describe_options
from ktdi.features import campaigns, help as help_feature
from tests.fakes import Ctx, Guild, User

SLASH_COMMANDS = ["abm", "anime", "bail", "bingo", "blame", "books", "bribe", "campaign", "committee", "expunge",
                  "help", "imperial", "linux", "loot", "np", "predict", "quote", "rapsheet", "rate", "rpg", "settings",
                  "shhh", "spray", "tdoi", "timezone", "whospray"]
SUBCOMMANDS = {
    "committee": ["funds", "ledger", "propose", "spend"],
    "np": ["elapsed", "end", "history", "pause", "predictions", "resume", "sct", "set", "show", "start", "vote",
           "watchlist"],
    "bingo": ["card", "mark", "unmark"],
    "timezone": ["clear", "convert", "set", "show"],
    "campaign": ["add", "edit", "list", "remind", "remove", "reschedule", "show", "skip", "unremind"],
    "quote": ["add", "claim", "delete", "dissociate", "last", "random", "search", "show"],
    "settings": ["shared_state", "show", "whospray_user"],
    "books": ["download", "search"],
    "rpg": ["download", "search"],
}


@pytest.fixture
def loaded_bot(monkeypatch):
    monkeypatch.setattr(campaigns.reminder_loop, "start", lambda: None)  # no background loop in tests
    bot = KTDIBot()

    async def load():
        await bot.load_features()
    asyncio.run(load())
    return bot


def test_slash_commands(loaded_bot):
    tree = loaded_bot.tree
    assert sorted(c.name for c in tree.get_commands(type=discord.AppCommandType.chat_input)) == SLASH_COMMANDS
    assert [c.name for c in tree.get_commands(type=discord.AppCommandType.message)] == ["Save quote"]
    for group, subs in SUBCOMMANDS.items():
        assert sorted(c.name for c in tree.get_command(group).commands) == subs
    watchlist = tree.get_command("np").get_command("watchlist")
    assert sorted(c.name for c in watchlist.commands) == ["add", "import", "remove", "show", "strike", "unstrike"]
    assert sorted(c.name for c in tree.get_command("np").get_command("vote").commands) == ["end", "start"]


def test_prefix_commands(loaded_bot):
    assert sorted(c.name for c in loaded_bot.commands) == SLASH_COMMANDS
    assert "anon" in [c.name for c in loaded_bot.get_command("quote").commands]  # !quote anon is prefix-only


def test_listeners(loaded_bot):
    assert {name: sorted(f.__name__ for f in funcs) for name, funcs in loaded_bot.extra_events.items()} == {
        "on_message": ["remember_speaker", "vote_closed_by_itself"],
        "on_raw_reaction_add": ["prediction_vote", "reminder_subscribe", "spray_reaction"],
        "on_raw_reaction_remove": ["prediction_unvote", "reminder_unsubscribe"],
    }


def all_commands(bot: commands.Bot):
    for command in bot.walk_commands():
        yield command


def test_every_help_page_fits_discord(loaded_bot):
    for command in all_commands(loaded_bot):
        embed = help_feature.command_help_embed(command)
        assert len(embed) <= help_feature.EMBED_TOTAL_LIMIT, command.qualified_name
        for field in embed.fields:
            assert len(field.value) <= help_feature.EMBED_FIELD_LIMIT, (command.qualified_name, field.name)


def test_help_details(loaded_bot):
    campaign = help_feature.command_help_embed(loaded_bot.get_command("campaign"))
    assert campaign.title == "/campaign"
    assert [f.name for f in campaign.fields if not f.name.startswith("/")] == [
        "📋 Setting up", "⏰ Reminders", "🗓️ When the game moves", "🔐 Who can change what", "⌨️ Typing it with !"]
    remind = help_feature.command_help_embed(loaded_bot.get_command("campaign remind"))
    assert "Also works as `!campaign remind`" in remind.description
    quote = help_feature.command_help_embed(loaded_bot.get_command("quote"))
    assert any(f.name == "!quote anon [text]" for f in quote.fields)
    assert any(f.name == "/quote add <text> [user] [context]" for f in quote.fields)
    abm = help_feature.command_help_embed(loaded_bot.get_command("abm"))
    assert "Type a number and a metric unit" in abm.description and len(abm.fields) == 12


def test_main_help_list(loaded_bot):
    ctx = Ctx(User(1, "scott"), Guild(111), bot=loaded_bot)
    asyncio.run(help_feature.help_command.callback(ctx))
    embed = ctx.last.embed
    assert ctx.last.view is None  # fits on one page, so no buttons
    assert [f.name for f in embed.fields] == [
        "💦 Rap sheet", "🎲 Fun", "🎬 Movie night", "📏 Measurements", "💬 Quotes", "🗓️ Campaigns",
        "🔧 Utilities"]
    fields = {f.name: f.value for f in embed.fields}
    assert "`/quote add | claim | delete | dissociate | last | random | search | show`: " in fields["💬 Quotes"]
    assert "`/bail <user> <amount>`: " in fields["💦 Rap sheet"] and "React 💦: " in fields["💦 Rap sheet"]
    assert "`/loot`: " in fields["🎲 Fun"] and "`/anime`: " in fields["🎲 Fun"]
    assert "/books" not in ctx.last.text and "/rpg" not in ctx.last.text  # library and rulebooks not set up here


def test_every_command_has_a_category_and_is_listed(loaded_bot, monkeypatch):
    monkeypatch.setattr(help_feature, "can_use", lambda command, ctx: True)  # include /books
    for command in loaded_bot.commands:
        assert help_feature.command_category(command) in help_feature.CATEGORY_ORDER, command.name
    ctx = Ctx(User(1, "scott"), Guild(111), bot=loaded_bot)
    text = "\n".join(f.value for page in help_feature.main_help_pages(ctx) for f in page.fields)
    for name in SLASH_COMMANDS:
        assert f"`/{name}" in text, name


def assert_fits(embed):
    assert len(embed) <= help_feature.EMBED_TOTAL_LIMIT
    assert len(embed.fields) <= help_feature.EMBED_FIELD_COUNT_LIMIT
    assert all(len(f.value) <= help_feature.EMBED_FIELD_LIMIT for f in embed.fields)


def test_main_help_list_fits_discord(loaded_bot, monkeypatch):
    monkeypatch.setattr(help_feature, "can_use", lambda command, ctx: True)
    pages = help_feature.main_help_pages(Ctx(User(1, "scott"), Guild(111), bot=loaded_bot))
    assert len(pages) == 1
    assert_fits(pages[0])


def test_long_categories_continue_in_another_field():
    lines = {"🎲 Fun": [f"`/cmd{i}`: " + "x" * 90 for i in range(30)], "💬 Quotes": ["`/quote`: q"]}
    fields = help_feature.category_fields(lines)
    assert [name for name, _ in fields] == ["🎲 Fun", "🎲 Fun (cont.)", "🎲 Fun (cont.)", "💬 Quotes"]
    assert all(len(value) <= help_feature.EMBED_FIELD_LIMIT for _, value in fields)
    assert "\n".join(value for _, value in fields[:3]).count("`/cmd") == 30  # nothing lost


def test_pagination_when_it_no_longer_fits():
    fields = [(f"Category {i}", "y" * 1000) for i in range(40)]
    pages = help_feature.paginate("Title", "Description", "Footer.", fields)
    assert len(pages) > 1
    for number, page in enumerate(pages, 1):
        assert_fits(page)
        assert page.footer.text == f"Page {number} of {len(pages)}. Footer."
    assert sum(len(page.fields) for page in pages) == 40  # nothing dropped
    many_small = help_feature.paginate("T", "D", "F", [(f"C{i}", "z") for i in range(60)])
    assert [len(page.fields) for page in many_small] == [25, 25, 10]


def test_help_buttons_flip_pages(loaded_bot, monkeypatch):
    from tests.fakes import Interaction
    monkeypatch.setattr(help_feature, "EMBED_FIELD_COUNT_LIMIT", 2)  # force several pages
    scott = User(1, "scott")
    ctx = Ctx(scott, Guild(111), bot=loaded_bot)

    async def go():
        await help_feature.help_command.callback(ctx)
        view = ctx.last.view
        assert isinstance(view, help_feature.HelpPages)
        assert len(view.pages) == -(-len(help_feature.CATEGORY_ORDER) // 2)  # two categories a page, rounded up
        assert view.previous_page.disabled and not view.next_page.disabled
        interaction = Interaction(scott)
        await view.next_page.callback(interaction)
        assert view.page == 1 and interaction.last.embed is view.pages[1]
        stranger = Interaction(User(2, "dave"))
        assert not await view.interaction_check(stranger)
        assert "Run your own `/help`" in stranger.last.content
        for _ in view.pages:
            await view.next_page.callback(interaction)
        assert view.page == len(view.pages) - 1 and view.next_page.disabled  # stops at the last page
    asyncio.run(go())


def test_help_unknown_command(loaded_bot):
    ctx = Ctx(User(1, "scott"), Guild(111), bot=loaded_bot)
    asyncio.run(help_feature.help_command.callback(ctx, command="nope"))
    assert ctx.last.content == "There's no `nope` command. Try `/help` for the list." and ctx.last.private


def test_command_logging_flattens_subcommands():
    options = [{"name": "search", "type": 1, "options": [{"name": "query", "value": "romance"}]}]
    assert describe_options(options) == "query=romance"
