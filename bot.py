import io
import logging
import os
import random
import sqlite3
import sys
from collections import defaultdict, deque
from logging.handlers import RotatingFileHandler
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

import abm
import library

BASE_DIR = Path(__file__).parent

# Run with --dev (e.g. "python bot.py --dev") to use the dev bot's settings in .env.dev.
ENV_FILE = ".env.dev" if "--dev" in sys.argv else ".env"
load_dotenv(BASE_DIR / ENV_FILE)

SPRAY_GIF_URL = "https://klipy.com/gifs/spray-bottle-3"
SPRAY_EMOJI = "💦"
LOOT_GIF_URL = "https://klipy.com/gifs/perception-check-tom-cardy"
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")


def parse_ids(*env_names: str) -> list[int]:
    """Comma-separated IDs from the first of these env vars that is set."""
    raw = next((os.getenv(name) for name in env_names if os.getenv(name)), "")
    return [int(i) for i in raw.replace(" ", "").split(",") if i]


# Comma-separated server IDs to register slash commands to (GUILD_ID also accepted).
GUILD_IDS = parse_ids("GUILD_IDS", "GUILD_ID")
# Calibre-Web library for /books. The commands only work in BOOKS_GUILD_IDS, and only if CALIBRE_URL is set.
BOOKS_GUILD_IDS = parse_ids("BOOKS_GUILD_IDS")
CALIBRE_URL = os.getenv("CALIBRE_URL")
BOOK_FORMATS = os.getenv("BOOK_FORMATS", "epub,kepub,azw3,mobi,pdf,cbz").replace(" ", "").split(",")
calibre = (
    library.CalibreWeb(CALIBRE_URL, os.getenv("CALIBRE_USERNAME", ""), os.getenv("CALIBRE_PASSWORD", ""), BOOK_FORMATS)
    if CALIBRE_URL else None
)
# Relative paths are resolved next to bot.py.
DB_PATH = str(BASE_DIR / os.getenv("DB_PATH", "ktdi.db"))
# Rolling log file (relative to bot.py). Rotates at LOG_MAX_BYTES, keeping LOG_BACKUPS old files.
LOG_FILE = BASE_DIR / os.getenv("LOG_FILE", "logs/ktdi-dev.log" if "--dev" in sys.argv else "logs/ktdi.log")
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", 1_000_000))
LOG_BACKUPS = int(os.getenv("LOG_BACKUPS", 5))
# Optional role given to each server's biggest briber. Skipped on servers without a role by this name.
BRIBER_ROLE_NAME = os.getenv("BRIBER_ROLE_NAME", "Champion Briber")

BLAME_LINES = [
    "This is {user}'s fault.",
    "After a thorough investigation, the committee blames {user}.",
    "{user} did this. Everyone saw it.",
    "Sources confirm: {user}.",
    "Not sure what happened, but it was definitely {user}.",
    "{user}, explain yourself.",
]

BRIBE_LINES = [
    "💰 {briber} slipped the committee **{amount}**. On review, this is actually {blamer}'s fault.",
    "💰 After receiving **{amount}** from {briber}, new evidence points to {blamer}.",
    "💰 {briber} paid **{amount}**. The committee now blames {blamer}. Justice is served.",
]

# The /linux target (@poltergeis.t). Override with LINUX_HATER_ID in .env.
LINUX_HATER_ID = os.getenv("LINUX_HATER_ID") or "351350774435151873"

LINUX_LINES = [
    "{user}, what're your opinions on Linux?",
    "{user}, how much do you hate Linux? Scale of 1 to 10, and 10 isn't high enough.",
    "{user}, quick question: is Linux the worst thing ever made, or just top three?",
    "{user}, if Linux were a person, what would you say to it?",
    "{user}, how many times this week has Linux personally wronged you?",
    "{user}, describe your relationship with Linux in one word. Keep it PG.",
    "{user}, someone just said \"it's the year of the Linux desktop\". Thoughts?",
    "{user}, would you rather use Linux for a week or step on Lego for a week?",
    "{user}, on a scale from \"mildly annoyed\" to \"burn it all down\", where does Linux sit today?",
    "{user}, what's your favourite thing about Linux? Trick question, we know the answer.",
    "{user}, how do you feel when someone says \"just compile it from source\"?",
    "{user}, if you had to explain your hatred of Linux to a child, how would you do it?",
    "{user}, we're taking a poll: how much do you hate Linux right now?",
    "{user}, Linux says hi. Would you like to say anything back?",
]

# Recent message authors per channel, used to pick someone to blame.
recent_speakers: dict[int, deque[int]] = defaultdict(lambda: deque(maxlen=50))

# Most recent blame per channel: channel_id -> (blamer_id, blamed_id).
last_blame: dict[int, tuple[int, int]] = {}


db = sqlite3.connect(DB_PATH)
db.execute(
    """
    CREATE TABLE IF NOT EXISTS sprays (
        guild_id INTEGER NOT NULL,
        user_id  INTEGER NOT NULL,
        count    INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    )
    """
)
db.execute(
    """
    CREATE TABLE IF NOT EXISTS bribes (
        guild_id INTEGER NOT NULL,
        user_id  INTEGER NOT NULL,
        count    INTEGER NOT NULL DEFAULT 0,
        total    INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    )
    """
)
db.execute(
    """
    CREATE TABLE IF NOT EXISTS briber_role_holders (
        guild_id INTEGER PRIMARY KEY,
        user_id  INTEGER NOT NULL
    )
    """
)
db.commit()


log = logging.getLogger("ktdi")


def setup_logging() -> None:
    """Log to the terminal (so journalctl still works) and to a rolling log file."""
    formatter = logging.Formatter("[{asctime}] [{levelname:<7}] {name}: {message}", "%Y-%m-%d %H:%M:%S", style="{")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)
    # The log file is best-effort: if it can't be opened, keep running with terminal/journal logging only.
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8")
    except OSError as error:
        log.warning("Couldn't open log file %s, logging to terminal only: %s", LOG_FILE, error)
        return
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)


def record_bribe(guild_id: int, user_id: int, amount: int) -> None:
    db.execute(
        """
        INSERT INTO bribes (guild_id, user_id, count, total) VALUES (?, ?, 1, ?)
        ON CONFLICT (guild_id, user_id) DO UPDATE SET count = count + 1, total = total + excluded.total
        """,
        (guild_id, user_id, amount),
    )
    db.commit()


def get_bribe_stats(guild_id: int, user_id: int) -> tuple[int, int]:
    row = db.execute(
        "SELECT count, total FROM bribes WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
    ).fetchone()
    return row if row else (0, 0)


def get_top_briber(guild_id: int) -> int | None:
    row = db.execute(
        "SELECT user_id FROM bribes WHERE guild_id = ? ORDER BY total DESC, user_id LIMIT 1", (guild_id,)
    ).fetchone()
    return row[0] if row else None


def get_briber_role_holder(guild_id: int) -> int | None:
    row = db.execute("SELECT user_id FROM briber_role_holders WHERE guild_id = ?", (guild_id,)).fetchone()
    return row[0] if row else None


def set_briber_role_holder(guild_id: int, user_id: int) -> None:
    db.execute(
        "INSERT INTO briber_role_holders (guild_id, user_id) VALUES (?, ?)"
        " ON CONFLICT (guild_id) DO UPDATE SET user_id = excluded.user_id",
        (guild_id, user_id),
    )
    db.commit()


async def get_member(guild: discord.Guild, user_id: int) -> discord.Member | None:
    try:
        return guild.get_member(user_id) or await guild.fetch_member(user_id)
    except discord.HTTPException:
        return None  # Left the server, or couldn't look them up.


async def update_briber_role(guild: discord.Guild) -> None:
    """Move the briber role to the server's biggest briber. Does nothing if the role or permission is missing."""
    role = discord.utils.get(guild.roles, name=BRIBER_ROLE_NAME)
    top_id = get_top_briber(guild.id)
    if role is None or top_id is None:
        return
    previous_id = get_briber_role_holder(guild.id)
    try:
        if previous_id and previous_id != top_id:
            previous = await get_member(guild, previous_id)
            if previous and role in previous.roles:
                await previous.remove_roles(role, reason="No longer the biggest briber")
                log.info("[%s] Took %r from %s", guild.name, BRIBER_ROLE_NAME, previous)
        top = await get_member(guild, top_id)
        if top and role not in top.roles:
            await top.add_roles(role, reason="Biggest briber")
            log.info("[%s] Gave %r to %s", guild.name, BRIBER_ROLE_NAME, top)
        set_briber_role_holder(guild.id, top_id)
    except discord.HTTPException as error:
        # Usually missing Manage Roles, or the role sits above the bot's own role.
        log.warning("[%s] Couldn't update %r role: %s", guild.name, BRIBER_ROLE_NAME, error)


def record_spray(guild_id: int, user_id: int) -> int:
    db.execute(
        """
        INSERT INTO sprays (guild_id, user_id, count) VALUES (?, ?, 1)
        ON CONFLICT (guild_id, user_id) DO UPDATE SET count = count + 1
        """,
        (guild_id, user_id),
    )
    db.commit()
    return get_spray_count(guild_id, user_id)


def get_spray_count(guild_id: int, user_id: int) -> int:
    row = db.execute(
        "SELECT count FROM sprays WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
    ).fetchone()
    return row[0] if row else 0


class KTDIBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        # Needed to read "<prefix>spray" from messages. Must also be enabled in the Developer Portal.
        intents.message_content = True
        super().__init__(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)

    async def setup_hook(self):
        if GUILD_IDS:
            # Server-only slash commands update instantly; global ones can take a while to reach clients.
            for guild_id in GUILD_IDS:
                guild = discord.Object(id=guild_id)
                self.tree.copy_global_to(guild=guild)
                if calibre is None or guild_id not in BOOKS_GUILD_IDS:
                    self.tree.remove_command("books", guild=guild)  # Don't show /books where it can't be used.
                synced = await self.tree.sync(guild=guild)
                log.info("Synced %d slash commands to server %s", len(synced), guild_id)
            # Remove any old global copies so commands don't show up twice.
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
        else:
            synced = await self.tree.sync()
            log.info("Synced %d global slash commands", len(synced))

    async def on_command(self, ctx: commands.Context):
        # Fires for both /commands and prefix commands.
        if ctx.interaction:
            invocation = f"/{ctx.command.qualified_name} {describe_options(ctx.interaction.data.get('options', []))}".strip()
        else:
            invocation = ctx.message.content
        where = f"{ctx.guild.name} #{ctx.channel}" if ctx.guild else "DM"
        log.info("[%s] %s ran %r", where, ctx.author, invocation)

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        # Tell people when they typed a command wrong instead of failing silently.
        if isinstance(error, (commands.UserInputError, commands.NoPrivateMessage)):
            log.info("%s's command failed: %s", ctx.author, error)
            await ctx.send(str(error), ephemeral=True)
        elif isinstance(error, commands.CheckFailure):
            log.info("%s can't use %s here: %s", ctx.author, ctx.command, error)
            await ctx.send(str(error) or "You can't use that here.", ephemeral=True)
        elif not isinstance(error, commands.CommandNotFound):
            await super().on_command_error(ctx, error)


def describe_options(options: list[dict]) -> str:
    """Slash command options as 'name=value', flattening subcommands like /books search."""
    parts = []
    for option in options:
        if "options" in option:
            parts.append(describe_options(option["options"]))
        elif "value" in option:
            parts.append(f"{option['name']}={option['value']}")
    return " ".join(p for p in parts if p)


bot = KTDIBot()


@bot.hybrid_command(name="spray", description="Spray the degenerate.")
@commands.guild_only()
async def spray(ctx: commands.Context, target: discord.Member | None = None):
    if target is None:
        await ctx.send(SPRAY_GIF_URL)
        return
    record_spray(ctx.guild.id, target.id)
    await ctx.send(f"{target.mention} {SPRAY_GIF_URL}")


@bot.hybrid_command(name="loot", description="Declare that you're looting the body.")
async def loot(ctx: commands.Context):
    await ctx.send(LOOT_GIF_URL)


@bot.hybrid_command(name="abm", description="Anything But Metric: convert a measurement into something absurd.")
async def abm_command(ctx: commands.Context, *, measurement: str):
    try:
        await ctx.send(abm.convert(measurement))
    except abm.ABMError as error:
        await ctx.send(str(error), ephemeral=True)


@bot.hybrid_command(name="imperial", description="Sincerely convert a metric measurement to imperial/US units.")
async def imperial_command(ctx: commands.Context, *, measurement: str):
    try:
        await ctx.send(abm.to_imperial(measurement))
    except abm.ABMError as error:
        await ctx.send(str(error), ephemeral=True)


def plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


@bot.hybrid_command(name="rapsheet", description="See someone's sprays and bribes.")
@commands.guild_only()
async def rapsheet(ctx: commands.Context, user: discord.Member | None = None):
    user = user or ctx.author
    sprays = get_spray_count(ctx.guild.id, user.id)
    bribes, bribe_total = get_bribe_stats(ctx.guild.id, user.id)
    if sprays == 0 and bribes == 0:
        await ctx.send(f"📋 {user.display_name} has a clean record. Suspicious.")
        return
    lines = [f"📋 **Rap sheet: {user.display_name}**"]
    if sprays:
        lines.append(f"Sprayed {plural(sprays, 'time')}.")
    if bribes:
        lines.append(f"Bribed the committee {plural(bribes, 'time')} (${bribe_total:,} total).")
        if get_top_briber(ctx.guild.id) == user.id:
            lines.append("👑 Biggest briber in the server.")
    await ctx.send("\n".join(lines))


@bot.hybrid_command(name="blame", description="Blame someone who's been talking recently.")
@commands.guild_only()
async def blame(ctx: commands.Context, *, reason: str | None = None):
    candidates = set(recent_speakers[ctx.channel.id]) or {ctx.author.id}
    blamed_id = random.choice(list(candidates))
    last_blame[ctx.channel.id] = (ctx.author.id, blamed_id)
    log.info("[%s] %s blamed user %s", ctx.guild.name, ctx.author, blamed_id)
    line = random.choice(BLAME_LINES).format(user=f"<@{blamed_id}>")
    if reason:
        line = f"**{reason}**\n{line}"
    await ctx.send(line)


@bot.hybrid_command(name="bribe", description="Blamed? Pay to put the blame back on whoever blamed you.")
@commands.guild_only()
async def bribe(ctx: commands.Context, amount: commands.Range[int, 1, 1_000_000_000_000]):
    blame_record = last_blame.get(ctx.channel.id)
    if blame_record is None:
        await ctx.send("Nobody's been blamed here. Save your money.", ephemeral=True)
        return
    blamer_id, blamed_id = blame_record
    if ctx.author.id != blamed_id:
        await ctx.send(f"You're not the one being blamed, <@{blamed_id}> is. Nice try.", ephemeral=True)
        return
    if blamer_id == blamed_id:
        await ctx.send("You blamed yourself. There's nobody to pass it to.", ephemeral=True)
        return
    record_bribe(ctx.guild.id, ctx.author.id, amount)
    # Flip the blame, so the original blamer can counter-bribe.
    last_blame[ctx.channel.id] = (blamed_id, blamer_id)
    log.info("[%s] %s bribed $%s, blame moved to user %s", ctx.guild.name, ctx.author, f"{amount:,}", blamer_id)
    await ctx.send(
        random.choice(BRIBE_LINES).format(briber=ctx.author.mention, blamer=f"<@{blamer_id}>", amount=f"${amount:,}")
    )
    await update_briber_role(ctx.guild)


@bot.hybrid_command(name="linux", description="Ask our resident Linux hater how he's feeling about Linux.")
async def linux(ctx: commands.Context):
    await ctx.send(random.choice(LINUX_LINES).format(user=f"<@{LINUX_HATER_ID}>"))


DM_FILE_SIZE_LIMIT = 10 * 1024 * 1024  # Discord's upload limit outside boosted servers.
SEARCH_RESULTS_SHOWN = 15
# Books seen in recent searches, so /books download <id> knows their formats and sizes.
recent_books: dict[int, library.Book] = {}


def books_available(guild: discord.Guild | None) -> bool:
    return calibre is not None and guild is not None and guild.id in BOOKS_GUILD_IDS


def books_enabled():
    async def predicate(ctx: commands.Context) -> bool:
        if calibre is None:
            raise commands.CheckFailure("The library isn't set up on this bot.")
        if not books_available(ctx.guild):
            raise commands.CheckFailure("The library isn't available in this server.")
        return True
    return commands.check(predicate)


def book_line(book: library.Book) -> str:
    title = discord.utils.escape_markdown(book.title[:80])
    formats = ", ".join(f.name.upper() for f in book.formats)
    return f"`{book.id}` **{title}** — {discord.utils.escape_markdown(book.author_text[:60])} ({formats})"


@bot.hybrid_group(name="books", description="Search and download books from the library.", invoke_without_command=True)
@books_enabled()
async def books(ctx: commands.Context):
    await ctx.send(
        "Use `/books search <anything>` to find books, then `/books download <title or ID>` to get one.",
        ephemeral=True,
    )


@books.command(name="search", description="Search the library by title, author, series or tag.")
@books_enabled()
async def books_search(ctx: commands.Context, *, query: str):
    await ctx.defer(ephemeral=True)
    try:
        results = await calibre.search(query)
    except library.LibraryError as error:
        log.warning("Library search for %r failed: %s", query, error)
        await ctx.send(str(error), ephemeral=True)
        return
    recent_books.update({book.id: book for book in results})
    if not results:
        await ctx.send(f"No books match “{discord.utils.escape_markdown(query)}”.", ephemeral=True)
        return
    embed = discord.Embed(
        title=f"📚 {len(results)} result{'s' if len(results) != 1 else ''} for “{query[:100]}”",
        description="\n".join(book_line(book) for book in results[:SEARCH_RESULTS_SHOWN]),
        color=discord.Color.blurple(),
    )
    footer = "Get one with /books download <ID or title>."
    if len(results) > SEARCH_RESULTS_SHOWN:
        footer = f"Showing {SEARCH_RESULTS_SHOWN} of {len(results)}. Narrow your search to see more. " + footer
    embed.set_footer(text=footer)
    await ctx.send(embed=embed, ephemeral=True)


async def find_book(query: str) -> library.Book | int | list[library.Book]:
    """A book ID, a single matching book, or a list of candidates if the title is ambiguous."""
    if query.isdigit():
        return recent_books.get(int(query)) or int(query)
    results = await calibre.search(query)
    recent_books.update({book.id: book for book in results})
    exact = [book for book in results if book.title.casefold() == query.casefold()]
    if len(exact) == 1 or len(results) == 1:
        return (exact or results)[0]
    return exact or results


@books.command(name="download", description="Download a book by ID or title. Only you will see it.")
@books_enabled()
async def books_download(ctx: commands.Context, *, book: str):
    await ctx.defer(ephemeral=True)
    # Slash replies can be private; prefix commands can't, so those go by DM instead.
    size_limit = ctx.guild.filesize_limit if ctx.interaction else DM_FILE_SIZE_LIMIT
    try:
        found = await find_book(book.strip())
        if isinstance(found, list):
            if not found:
                await ctx.send(f"No books match “{discord.utils.escape_markdown(book)}”.", ephemeral=True)
            else:
                lines = "\n".join(book_line(b) for b in found[:10])
                await ctx.send(f"Several books match. Download one by its ID:\n{lines}", ephemeral=True)
            return
        if isinstance(found, int):
            download = await calibre.download_by_id(found, size_limit)
            title = download.filename.rsplit(".", 1)[0]
        else:
            download = await calibre.download(found, size_limit)
            title = found.title
    except library.LibraryError as error:
        log.warning("Library download for %r failed: %s", book, error)
        await ctx.send(str(error), ephemeral=True)
        return

    log.info("[%s] %s downloaded %r (%s)", ctx.guild.name, ctx.author, download.filename,
             library.format_size(len(download.data)))
    message = f"📖 **{discord.utils.escape_markdown(title)}**"
    file = discord.File(io.BytesIO(download.data), filename=download.filename)
    if ctx.interaction:
        await ctx.send(message, file=file, ephemeral=True)
        return
    try:
        await ctx.author.send(message, file=file)
        await ctx.reply("📬 Sent it to your DMs.")
    except discord.Forbidden:
        await ctx.reply("I couldn't DM you. Allow DMs from server members, or use `/books download` instead.")


def can_use(command: commands.Command, ctx: commands.Context) -> bool:
    """Whether to show a command in /help here."""
    if (command.root_parent or command).name == "books":
        return books_available(ctx.guild)
    return True


def command_help_embed(command: commands.Command) -> discord.Embed:
    """Detailed help for one command, e.g. /help abm."""
    embed = discord.Embed(
        title=f"/{command.name} {command.signature}".strip(),
        description=f"{command.description}\n\nAlso works as `{COMMAND_PREFIX}{command.name}`.",
        color=discord.Color.blurple(),
    )
    if isinstance(command, commands.Group):
        embed.description = f"{command.description}\n\nAlso works as `{COMMAND_PREFIX}{command.name} <subcommand>`."
        for sub in sorted(command.commands, key=lambda c: c.name):
            embed.add_field(name=f"/{sub.qualified_name} {sub.signature}".strip(), value=sub.description, inline=False)
    if command.name == "books":
        embed.add_field(
            name="Privacy",
            value=(f"With `/books`, search results and books are only shown to you. With `{COMMAND_PREFIX}books`, "
                   f"search results post in the channel and books are sent by DM."),
            inline=False,
        )
    if command.name in ("abm", "imperial"):
        embed.description += (
            "\n\nType a number and a metric unit, with or without a space: `3cm`, `2.5 kg`, `100 km/h`. "
            "Spelled-out names like `metres` or `litres` work too. Capitals mostly don't matter, "
            "except `mW` vs `MW`."
        )
        for dimension, units in abm.input_unit_help():
            embed.add_field(name=dimension, value=units, inline=True)
    return embed


@bot.hybrid_command(name="help", description="List everything this bot can do, or details for one command.")
async def help_command(ctx: commands.Context, command: str | None = None):
    if command:
        found = bot.get_command(command.lstrip("/" + COMMAND_PREFIX).lower())
        if found is None or not can_use(found, ctx):
            await ctx.send(f"There's no `{command}` command. Try `/help` for the list.", ephemeral=True)
        else:
            # Private for /help <command>, so the details don't fill the channel.
            await ctx.send(embed=command_help_embed(found), ephemeral=True)
        return
    embed = discord.Embed(
        title="Keep The Degenerates Inline",
        description=f"Use `/command` or `{COMMAND_PREFIX}command`.",
        color=discord.Color.blurple(),
    )
    for command in sorted(bot.commands, key=lambda c: c.name):
        if not can_use(command, ctx):
            continue  # e.g. /books outside the library servers.
        usage = " | ".join(sub.name for sub in command.commands) if isinstance(command, commands.Group) else command.signature
        embed.add_field(
            name=f"/{command.name} {usage}".strip(),
            value=command.description or "No description.",
            inline=False,
        )
    embed.add_field(
        name=f"React {SPRAY_EMOJI}",
        value="Sprays whoever sent the message and adds to their rap sheet.",
        inline=False,
    )
    embed.set_footer(text="Use /help <command> for details, e.g. /help abm for every unit it understands.")
    await ctx.send(embed=embed)


@bot.listen()
async def on_message(message: discord.Message):
    if message.guild and not message.author.bot:
        recent_speakers[message.channel.id].append(message.author.id)


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    # Reacting 💦 to a message sprays whoever sent it.
    if str(payload.emoji) != SPRAY_EMOJI or payload.user_id == bot.user.id:
        return
    channel = bot.get_channel(payload.channel_id)
    if channel is None:
        return
    target = ""
    if payload.message_author_id:
        target = f"<@{payload.message_author_id}> "
        if payload.guild_id:
            record_spray(payload.guild_id, payload.message_author_id)
    reactor = payload.member or f"user {payload.user_id}"
    log.info("[%s] %s reacted %s, spraying user %s", channel.guild if payload.guild_id else "DM",
             reactor, SPRAY_EMOJI, payload.message_author_id)
    await channel.send(f"{target}{SPRAY_GIF_URL}")


@bot.event
async def on_ready():
    log.info("Logged in as %s (ID: %s), prefix: %r, logging to %s", bot.user, bot.user.id, COMMAND_PREFIX, LOG_FILE)


def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit(f"DISCORD_TOKEN is not set. Copy .env.example to {ENV_FILE} and add your token.")
    setup_logging()
    # log_handler=None: use the logging set up above instead of discord.py's default.
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
