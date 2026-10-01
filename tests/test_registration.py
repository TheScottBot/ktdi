"""Loading every feature onto a real bot registers the expected commands, and /help stays within Discord's limits."""

import asyncio

import discord
import pytest
from discord.ext import commands

from ktdi.bot import KTDIBot, describe_options
from ktdi.features import campaigns, help as help_feature
from tests.fakes import Ctx, Guild, User

SLASH_COMMANDS = ["abm", "anime", "bail", "blame", "books", "bribe", "campaign", "expunge", "help", "imperial", "linux",
                  "loot", "quote",
                  "rapsheet", "settings", "spray", "tdoi", "whospray"]
SUBCOMMANDS = {
    "campaign": ["add", "edit", "list", "remind", "remove", "reschedule", "show", "skip", "unremind"],
    "quote": ["add", "claim", "delete", "dissociate", "last", "random", "search", "show"],
    "settings": ["shared_state", "show", "whospray_user"],
    "books": ["download", "search"],
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


def test_prefix_commands(loaded_bot):
    assert sorted(c.name for c in loaded_bot.commands) == SLASH_COMMANDS
    assert "anon" in [c.name for c in loaded_bot.get_command("quote").commands]  # !quote anon is prefix-only


def test_listeners(loaded_bot):
    assert {name: sorted(f.__name__ for f in funcs) for name, funcs in loaded_bot.extra_events.items()} == {
        "on_message": ["remember_speaker"],
        "on_raw_reaction_add": ["reminder_subscribe", "spray_reaction"],
        "on_raw_reaction_remove": ["reminder_unsubscribe"],
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
    names = [f.name for f in ctx.last.embed.fields]
    assert "/quote add | claim | delete | dissociate | last | random | search | show" in names
    assert "React 💦" in names
    assert not any(n.startswith("/books") for n in names)  # library not set up here


def test_help_unknown_command(loaded_bot):
    ctx = Ctx(User(1, "scott"), Guild(111), bot=loaded_bot)
    asyncio.run(help_feature.help_command.callback(ctx, command="nope"))
    assert ctx.last.content == "There's no `nope` command. Try `/help` for the list." and ctx.last.private


def test_command_logging_flattens_subcommands():
    options = [{"name": "search", "type": 1, "options": [{"name": "query", "value": "romance"}]}]
    assert describe_options(options) == "query=romance"
