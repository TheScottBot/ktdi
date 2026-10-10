"""Loading every feature onto a real bot registers the expected commands, and /help stays within Discord's limits."""

import asyncio

import discord
import pytest
from discord.ext import commands

from ktdi.bot import KTDIBot, describe_options
from ktdi.features import campaigns, help as help_feature
from tests.fakes import Ctx, Guild, User

SLASH_COMMANDS = ["abm", "anime", "bad", "badbonk", "bail", "blame", "books", "bribe", "campaign", "committee",
                  "expunge", "hammeredofwitches", "help", "herbal", "imperial", "linux", "loot", "nowplaying",
                  "quote", "rapsheet", "rpg", "settings", "shhh", "spray", "sprayfutures", "sprayrate", "tdoi",
                  "timezone", "whospray"]
PREFIX_ONLY_COMMANDS = ["toenoyoudidnt"]  # !-only, so they're not in Discord's slash menu
HIDDEN_COMMANDS = ["toenoyoudidnt"]  # cryptids: real commands, left off the /help list
SUBCOMMANDS = {
    "committee": ["funds", "ledger", "propose", "spend"],
    "nowplaying": ["bingo", "elapsed", "end", "history", "pause", "predict", "predictions", "rate", "resume", "sct",
                   "set", "show", "start", "vote", "watchlist"],
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
    nowplaying = tree.get_command("nowplaying")
    watchlist = nowplaying.get_command("watchlist")
    assert sorted(c.name for c in watchlist.commands) == ["add", "import", "remove", "show", "strike", "unstrike"]
    assert sorted(c.name for c in nowplaying.get_command("vote").commands) == ["end", "start"]
    assert sorted(c.name for c in nowplaying.get_command("bingo").commands) == ["card", "mark", "unmark"]
    assert tree.get_command("np") is None  # slash commands can't have aliases: /nowplaying only


def test_np_still_works_typed(loaded_bot):
    assert loaded_bot.get_command("np") is loaded_bot.get_command("nowplaying")
    assert loaded_bot.get_command("np bingo card") is loaded_bot.get_command("nowplaying bingo card")
    assert loaded_bot.get_command("np countdown") is loaded_bot.get_command("nowplaying start")


def test_prefix_commands(loaded_bot):
    assert sorted(c.name for c in loaded_bot.commands) == sorted(SLASH_COMMANDS + PREFIX_ONLY_COMMANDS)
    assert "anon" in [c.name for c in loaded_bot.get_command("quote").commands]  # !quote anon is prefix-only


def test_listeners(loaded_bot):
    assert {name: sorted(f.__name__ for f in funcs) for name, funcs in loaded_bot.extra_events.items()} == {
        "on_message": ["remember_speaker", "vote_closed_by_itself"],
        "on_raw_reaction_add": ["dig", "prediction_vote", "reminder_subscribe", "spray_reaction"],
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
        assert (f"`/{name}" in text) == (name not in HIDDEN_COMMANDS), name


def test_cryptids_are_unlisted_but_real(loaded_bot):
    assert sorted(c.name for c in loaded_bot.commands if c.extras.get("hidden")) == HIDDEN_COMMANDS
    ctx = Ctx(User(1, "scott"), Guild(111), bot=loaded_bot)
    asyncio.run(help_feature.help_command.callback(ctx, command="toenoyoudidnt"))
    assert ctx.last.embed.title == "!toenoyoudidnt"  # if you know, you know
    assert "Only works typed with `!`" in ctx.last.embed.description
    assert loaded_bot.tree.get_command("toenoyoudidnt") is None  # not in Discord's slash menu


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


def test_one_unreachable_server_doesnt_stop_startup(monkeypatch, caplog):
    import types
    from ktdi import config
    monkeypatch.setattr(campaigns.reminder_loop, "start", lambda: None)
    monkeypatch.setattr(config, "GUILD_IDS", [111, 222, 333])
    bot = KTDIBot()
    synced = []

    async def sync(guild=None):
        if guild is not None and guild.id == 222:  # the bot isn't in this one
            raise discord.Forbidden(types.SimpleNamespace(status=403, reason="Forbidden"),
                                    {"code": 50001, "message": "Missing Access"})
        synced.append(guild.id if guild else "global")
        return []
    monkeypatch.setattr(bot.tree, "sync", sync)
    caplog.set_level("WARNING", logger="ktdi")
    asyncio.run(bot.setup_hook())
    assert synced == [111, 333, "global"]  # the others still got their commands
    assert "Couldn't add slash commands to server 222" in caplog.text


def test_readme_covers_every_command_and_feature(loaded_bot):
    """The README lists every command, subcommand and feature file, and no cryptids (they're found, not documented)."""
    import pathlib
    import re
    from ktdi.features import FEATURES
    root = pathlib.Path(__file__).resolve().parent.parent
    readme = (root / "README.md").read_text(encoding="utf-8")
    for command in loaded_bot.walk_commands():
        root_command = command.root_parent or command
        if root_command.extras.get("hidden"):
            assert command.name not in readme, f"cryptid {command.qualified_name} is in the README"
            continue
        assert f"`{root_command.name}" in readme or f"`!{root_command.name}" in readme, command.qualified_name
        assert re.search(rf"\b{re.escape(command.name)}\b", readme), command.qualified_name
    for feature in FEATURES:
        assert f"{feature.rsplit('.', 1)[1]}.py" in readme, feature


def test_env_example_covers_every_setting():
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parent.parent
    config_source = (root / "ktdi" / "config.py").read_text(encoding="utf-8")
    example = (root / ".env.example").read_text(encoding="utf-8")
    settings = set(re.findall(r'(?:getenv|parse_ids|zone_setting|time_setting)\("([A-Z_]+)"', config_source))
    assert settings, "found no settings"
    internal = {"KTDI_NO_DOTENV"}  # for the tests, not for people
    missing = sorted(name for name in settings - internal if name not in example)
    assert not missing, f"not in .env.example: {missing}"
