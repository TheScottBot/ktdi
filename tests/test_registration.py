"""Loading every feature onto a real bot registers the expected commands, and /help stays within Discord's limits."""

import asyncio

import discord
import pytest
from discord.ext import commands

from ktdi import daily
from ktdi.bot import KTDIBot, describe_options
from ktdi.features import campaigns, help as help_feature
from tests.fakes import Ctx, Guild, User

SLASH_COMMANDS = ["abm", "almanac", "anime", "bad", "badbonk", "bail", "beeton", "bestiary", "blame", "books", "bribe", "campaign", "committee",
                  "cure", "deadword", "devils", "dream", "enquire", "etiquette", "expunge", "hammeredofwitches", "help", "herbal", "imperial", "insurance", "linux", "loot", "lore", "melancholy",
                  "nowplaying", "phrase", "plant", "pliny", "pseudodoxia", "quote", "rapsheet", "rpg", "secrets", "settings", "shhh", "spray", "sprayfutures", "sprayrate",
                  "tdoi", "timezone", "vulgartongue", "wars", "weather", "whospray", "wisdom", "wonder"]
PREFIX_ONLY_COMMANDS = ["toenoyoudidnt"]  # !-only, so they're not in Discord's slash menu
HIDDEN_COMMANDS = ["toenoyoudidnt"]  # cryptids: real commands, left off the /help list
SUBCOMMANDS = {
    "almanac": ["day", "setup"],
    "beeton": ["advice", "menu", "recipe"],
    "committee": ["funds", "ledger", "propose", "spend"],
    "etiquette": ["gentleman", "gentlethem", "gentlewoman", "remind"],
    "vulgartongue": ["insult", "lookup", "random"],
    "weather": ["here", "in"],
    "wisdom": ["now", "setup"],
    "insurance": ["buy", "complain", "status"],
    "nowplaying": ["bingo", "canon", "committeesviews", "elapsed", "end", "history", "objection", "pause", "predict",
                   "predictions", "rate", "resume", "sct", "set", "show", "start", "vote", "watchlist"],
    "timezone": ["clear", "convert", "set", "show"],
    "campaign": ["add", "edit", "list", "remind", "remove", "reschedule", "show", "skip", "unremind"],
    "quote": ["add", "claim", "delete", "dissociate", "last", "random", "search", "show"],
    "settings": ["shared_state", "show", "whospray_user"],
    "books": ["download", "search"],
    "rpg": ["download", "search"],
}


@pytest.fixture
def loaded_bot(monkeypatch):
    monkeypatch.setattr(campaigns.reminder_loop, "start", lambda: None)  # no background loops in tests
    monkeypatch.setattr(daily.daily_loop, "start", lambda: None)
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
    assert sorted(c.name for c in nowplaying.get_command("vote").commands) == ["end", "show", "start"]
    assert sorted(c.name for c in nowplaying.get_command("bingo").commands) == ["card", "mark", "unmark"]
    for group in ("wisdom", "almanac"):
        assert sorted(c.name for c in tree.get_command(group).get_command("setup").commands) == ["here", "show", "stop"]
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
    assert "Also works typed as `!campaign remind`." in remind.description
    quote = help_feature.command_help_embed(loaded_bot.get_command("quote"))
    assert any(f.name == "!quote anon [text]" for f in quote.fields)
    assert any(f.name == "/quote add <text> [user] [context]" for f in quote.fields)
    abm = help_feature.command_help_embed(loaded_bot.get_command("abm"))
    assert "Type a number and a metric unit" in abm.description and len(abm.fields) == 12


def test_help_front_page(loaded_bot):
    ctx = Ctx(User(1, "scott"), Guild(111), bot=loaded_bot)
    asyncio.run(help_feature.help_command.callback(ctx))
    embed = ctx.last.embed
    assert not ctx.last.private  # In the channel, so others see where to start too
    lines = embed.description.split("\n")
    assert lines[0] == "**Start here:** `/spray` · `/rapsheet` · `/bad` · `/quote random` · `/nowplaying`"
    sections = [line for line in lines[2:]]
    assert [line.split(" **")[1].split("**")[0] for line in sections] == [
        "Rap sheet", "Fun", "Words & wisdom", "Beasts & magic", "Hearth & herbs", "Movie night", "Measurements", "Quotes",
        "Campaigns", "Utilities"]
    assert sections[3].startswith("🐉 **Beasts & magic**: Monsters, marvels, curiosities, spells, witches and dreams (")
    assert not embed.fields and len(embed) < 1500  # Short: one line a section
    assert isinstance(ctx.last.view, help_feature.HelpMenu)
    assert [o.label for o in ctx.last.view.sections.options][:3] == ["Rap sheet", "Fun", "Words & wisdom"]


def test_the_menu_opens_a_section_privately(loaded_bot):
    from tests.fakes import Interaction
    ctx = Ctx(User(1, "scott"), Guild(111), bot=loaded_bot)

    async def go():
        await help_feature.help_command.callback(ctx)
        view = ctx.last.view
        view.sections._values = ["🐉 Beasts & magic"]
        dave = Interaction(User(2, "dave"))  # Anyone can use it: the section is shown just to them
        await view.sections.callback(dave)
        assert dave.last.embed.title == "🐉 Beasts & magic" and dave.last.private
        assert "`/dream [thing]`: " in dave.last.embed.description
    asyncio.run(go())


def test_section_pages(loaded_bot):
    ctx = Ctx(User(1, "scott"), Guild(111), bot=loaded_bot)
    lines = help_feature.main_help_lines(ctx)
    quotes = help_feature.section_page("💬 Quotes", lines["💬 Quotes"])
    assert "`/quote …`: Save and replay" in quotes.description  # Subcommands are on /help quote, not here
    rap = help_feature.section_page("💦 Rap sheet", lines["💦 Rap sheet"]).description
    assert rap.startswith("Sprays, telling-offs, blame, bribes and the committee\n\n")
    assert "`/bad [user]`: " in rap and "`/badbonk [user]`: " in rap  # Telling-offs go on the rap sheet
    assert "`/bail <user> <amount>`: " in rap and "React 💦: " in rap
    fun = help_feature.section_page("🎲 Fun", lines["🎲 Fun"]).description
    assert "`/loot`: " in fun and "`/anime`: " in fun
    assert "/books" not in str(lines) and "/rpg" not in str(lines)  # Library and rulebooks not set up here


def test_help_for_a_section_by_name(loaded_bot):
    ctx = Ctx(User(1, "scott"), Guild(111), bot=loaded_bot)
    for typed, section in [("beasts and magic", "🐉 Beasts & magic"), ("Beasts & Magic", "🐉 Beasts & magic"),
                           ("magic", "🐉 Beasts & magic"), ("hearth", "🌿 Hearth & herbs"), ("rap sheet", "💦 Rap sheet"),
                           ("movie", "🎬 Movie night"), ("words and wisdom", "📚 Words & wisdom")]:
        asyncio.run(help_feature.help_command.callback(ctx, command=typed))
        assert ctx.last.private and ctx.last.embed.title == section, typed
    asyncio.run(help_feature.help_command.callback(ctx, command="spray"))
    assert ctx.last.embed.title.startswith("/spray")  # A command's own name wins


def test_every_command_has_a_section_and_is_listed(loaded_bot, monkeypatch):
    monkeypatch.setattr(help_feature, "can_use", lambda command, ctx: True)  # include /books
    for command in loaded_bot.commands:
        assert help_feature.command_category(command) in help_feature.CATEGORIES, command.name
    ctx = Ctx(User(1, "scott"), Guild(111), bot=loaded_bot)
    text = "\n".join(line for lines in help_feature.main_help_lines(ctx).values() for line in lines)
    for name in SLASH_COMMANDS:
        assert (f"`/{name}" in text) == (name not in HIDDEN_COMMANDS), name


def test_cryptids_are_unlisted_but_real(loaded_bot):
    assert sorted(c.name for c in loaded_bot.commands if c.extras.get("hidden")) == HIDDEN_COMMANDS
    ctx = Ctx(User(1, "scott"), Guild(111), bot=loaded_bot)
    asyncio.run(help_feature.help_command.callback(ctx, command="toenoyoudidnt"))
    assert ctx.last.embed.title == "!toenoyoudidnt"  # if you know, you know
    assert "Only works typed with `!`" in ctx.last.embed.description
    assert loaded_bot.tree.get_command("toenoyoudidnt") is None  # not in Discord's slash menu


def test_every_help_page_fits_discord_even_with_everything(loaded_bot, monkeypatch):
    monkeypatch.setattr(help_feature, "can_use", lambda command, ctx: True)
    ctx = Ctx(User(1, "scott"), Guild(111), bot=loaded_bot)
    lines = help_feature.main_help_lines(ctx)
    pages = [help_feature.front_page(ctx, lines)] + [help_feature.section_page(c, ls) for c, ls in lines.items()]
    for page in pages:
        assert len(page) <= help_feature.EMBED_TOTAL_LIMIT and len(page.description) <= 4096, page.title
    assert len(lines) <= 25  # The menu holds 25 sections


def test_a_group_lists_its_own_slash_subcommand(loaded_bot):
    beeton = help_feature.command_help_embed(loaded_bot.get_command("beeton"))
    assert [f.name for f in beeton.fields if f.name.startswith("/")] == [
        "/beeton advice [topic]", "/beeton menu [day]", "/beeton recipe [dish]"]  # "recipe" is /beeton itself


def test_help_unknown_command(loaded_bot):
    ctx = Ctx(User(1, "scott"), Guild(111), bot=loaded_bot)
    asyncio.run(help_feature.help_command.callback(ctx, command="zzqx"))
    assert ctx.last.content == "There's no `zzqx` command or section. Try `/help` for the list." and ctx.last.private


def test_command_logging_flattens_subcommands():
    options = [{"name": "search", "type": 1, "options": [{"name": "query", "value": "romance"}]}]
    assert describe_options(options) == "query=romance"


def test_one_unreachable_server_doesnt_stop_startup(monkeypatch, caplog):
    import types
    from ktdi import config
    monkeypatch.setattr(campaigns.reminder_loop, "start", lambda: None)
    monkeypatch.setattr(daily.daily_loop, "start", lambda: None)
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


def test_help_shows_every_way_to_type_a_command(loaded_bot):
    devils = help_feature.command_help_embed(loaded_bot.get_command("devils"))
    assert "Also works typed as `!devils`, `!devil`, `!devilsdictionary`." in devils.description
    slang = help_feature.command_help_embed(loaded_bot.get_command("vulgartongue"))
    assert "`!vulgartongue <subcommand>`, `!vt <subcommand>`, `!slang <subcommand>`" in slang.description


def test_every_command_has_more_help_than_its_one_line(loaded_bot):
    # The section pages show each command's one-line description; /help <command> has to say more.
    for command in loaded_bot.commands:
        if command.extras.get("hidden"):
            continue
        embed = help_feature.command_help_embed(command)
        extra_fields = [f for f in embed.fields if not f.name.startswith(("/", "!"))]
        assert command.help or extra_fields, f"/help {command.name} only repeats its one-line description"


def test_help_text_reads_as_paragraphs(loaded_bot):
    spray = help_feature.command_help_embed(loaded_bot.get_command("spray"))
    assert "goes on their rap sheet, unless their spray insurance covers it" in spray.description  # Not broken up


def test_help_autocompletes_sections_and_commands(loaded_bot):
    from tests.fakes import Interaction
    interaction = Interaction(User(1, "scott"), Guild(111))
    interaction.client = loaded_bot

    def suggest(typed):
        return [(c.name, c.value) for c in asyncio.run(help_feature.command_autocomplete(interaction, typed))]

    assert [value for _, value in suggest("")[:10]] == [
        "Rap sheet", "Fun", "Words & wisdom", "Beasts & magic", "Hearth & herbs", "Movie night", "Measurements", "Quotes",
        "Campaigns", "Utilities"]  # The sections first
    assert [value for _, value in suggest("bee")] == ["beeton", "beeton advice", "beeton menu"]
    assert ("nowplaying (also np)", "nowplaying") in suggest("np")  # Found by the name people type
    assert ("devils (also devil, devilsdictionary)", "devils") in suggest("devil")
    assert ("nowplaying vote show (also where, link)", "nowplaying vote show") in suggest("vote show")
    assert suggest("hearth")[0] == ("Hearth & herbs", "Hearth & herbs")
    assert not any("toenoyoudidnt" in value for _, value in suggest("toe"))  # Cryptids stay secret
    assert not any(value.startswith(("books", "rpg")) for _, value in suggest(""))  # Not set up on this server
    assert len(suggest("")) == 25 and all(len(n) <= 100 and len(v) <= 100 for n, v in suggest("e"))  # Discord's limits

    # Every suggestion works when picked.
    ctx = Ctx(User(1, "scott"), Guild(111), bot=loaded_bot)
    for _, topic in help_feature.help_topics(loaded_bot, interaction):
        asyncio.run(help_feature.help_command.callback(ctx, command=topic))
        assert ctx.last.embed is not None, topic
