"""The bot itself: startup, loading features, syncing slash commands, command logging and errors."""

import logging
from logging.handlers import RotatingFileHandler

import discord
from discord.ext import commands

from ktdi import common, config, db
from ktdi.common import log
from ktdi.features import FEATURES


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
        config.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(config.LOG_FILE, maxBytes=config.LOG_MAX_BYTES,
                                           backupCount=config.LOG_BACKUPS, encoding="utf-8")
    except OSError as error:
        log.warning("Couldn't open log file %s, logging to terminal only: %s", config.LOG_FILE, error)
        return
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)


def is_private_command(ctx: commands.Context) -> bool:
    """Commands marked private (the library) are never logged with who used them or what they looked for."""
    return ctx.command is not None and (ctx.command.root_parent or ctx.command).extras.get("private", False)


def describe_options(options: list[dict]) -> str:
    """Slash command options as 'name=value', flattening subcommands like /books search."""
    parts = []
    for option in options:
        if "options" in option:
            parts.append(describe_options(option["options"]))
        elif "value" in option:
            parts.append(f"{option['name']}={option['value']}")
    return " ".join(p for p in parts if p)


class KTDIBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        # Needed to read "<prefix>spray" from messages. Must also be enabled in the Developer Portal.
        intents.message_content = True
        super().__init__(command_prefix=config.COMMAND_PREFIX, intents=intents, help_command=None)

    async def load_features(self) -> None:
        for feature in FEATURES:
            await self.load_extension(feature)

    async def setup_hook(self):
        await self.load_features()
        if config.GUILD_IDS:
            # Server-only slash commands update instantly; global ones can take a while to reach clients.
            for guild_id in config.GUILD_IDS:
                guild = discord.Object(id=guild_id)
                self.tree.copy_global_to(guild=guild)
                if not config.CALIBRE_URL or guild_id not in config.BOOKS_GUILD_IDS:
                    self.tree.remove_command("books", guild=guild)  # Don't show /books where it can't be used.
                synced = await self.tree.sync(guild=guild)
                log.info("Synced %d slash commands to server %s", len(synced), guild_id)
            # Remove any old global copies so commands don't show up twice.
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
        else:
            if not config.CALIBRE_URL:
                self.tree.remove_command("books")  # Library not set up, so don't show /books anywhere.
            synced = await self.tree.sync()
            log.info("Synced %d global slash commands", len(synced))

    async def on_ready(self):
        log.info("Logged in as %s (ID: %s), prefix: %r, logging to %s", self.user, self.user.id,
                 config.COMMAND_PREFIX, config.LOG_FILE)

    async def on_command(self, ctx: commands.Context):
        # Fires for both /commands and prefix commands.
        if is_private_command(ctx):
            return  # Library use isn't logged, so nobody's reading is tied back to them.
        if ctx.interaction:
            invocation = f"/{ctx.command.qualified_name} {describe_options(ctx.interaction.data.get('options', []))}".strip()
        else:
            invocation = ctx.message.content
        where = f"{ctx.guild.name} #{ctx.channel}" if ctx.guild else "DM"
        log.info("[%s] %s ran %r", where, ctx.author, invocation)

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        # Tell people when they typed a command wrong instead of failing silently.
        who = "Someone" if is_private_command(ctx) else str(ctx.author)
        if isinstance(error, (commands.UserInputError, commands.NoPrivateMessage)):
            log.info("%s's %s command failed: %s", who, ctx.command, error)
            await ctx.send(str(error), ephemeral=True)
        elif isinstance(error, commands.CheckFailure):
            log.info("%s can't use %s here: %s", who, ctx.command, error)
            await ctx.send(str(error) or "You can't use that here.", ephemeral=True)
        elif not isinstance(error, commands.CommandNotFound):
            await super().on_command_error(ctx, error)


def create_bot() -> KTDIBot:
    db.init(config.DB_PATH)
    common.bot = KTDIBot()
    return common.bot


def main():
    if not config.DISCORD_TOKEN:
        raise SystemExit(f"DISCORD_TOKEN is not set. Copy .env.example to {config.ENV_FILE} and add your token.")
    setup_logging()
    # log_handler=None: use the logging set up above instead of discord.py's default.
    create_bot().run(config.DISCORD_TOKEN, log_handler=None)
