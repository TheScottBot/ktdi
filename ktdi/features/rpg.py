"""/rpg: search the RPG rulebooks in a Dropbox folder and get a download link.

Like /books, private by design: marked extras["private"], so the bot never logs who searched for or downloaded what.
Downloads are Dropbox's own temporary links (4 hours), because rulebooks are usually too big to upload to Discord.
"""

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import config
from ktdi.common import SearchPages, log, send_search_pages
from ktdi.lib import dropbox
from ktdi.lib.library import format_size

HELP_CATEGORY = "🔧 Utilities"
SEARCH_RESULTS_SHOWN = 15

# Needs every setting, including the folder: without RPG_DROPBOX_PATH it would be the whole Dropbox.
rulebooks = (
    dropbox.Dropbox(config.DROPBOX_APP_KEY, config.DROPBOX_APP_SECRET, config.DROPBOX_REFRESH_TOKEN,
                    config.RPG_DROPBOX_PATH)
    if all((config.DROPBOX_APP_KEY, config.DROPBOX_APP_SECRET, config.DROPBOX_REFRESH_TOKEN,
            config.RPG_DROPBOX_PATH.strip("/")))
    else None
)
# The numbers shown in recent searches, so /rpg download 12 gets the file that was 12 then.
recent_files: dict[int, dropbox.RpgFile] = {}


def rpg_configured() -> bool:
    return rulebooks is not None


def rpg_available(guild: discord.Guild | None) -> bool:
    return rulebooks is not None and guild is not None and guild.id in config.RPG_GUILD_IDS


def rpg_enabled():
    async def predicate(ctx: commands.Context) -> bool:
        if rulebooks is None:
            raise commands.CheckFailure("The RPG rulebooks aren't set up on this bot.")
        if not rpg_available(ctx.guild):
            raise commands.CheckFailure("The RPG rulebooks aren't available in this server.")
        return True
    return commands.check(predicate)


def file_line(number: int, file: dropbox.RpgFile) -> str:
    folder = f" — {discord.utils.escape_markdown(file.folder[:60])}" if file.folder else ""
    return f"`{number}` **{discord.utils.escape_markdown(file.name[:80])}**{folder} ({format_size(file.size)})"


async def numbered(files: list[dropbox.RpgFile]) -> list[tuple[int, dropbox.RpgFile]]:
    """Each file with its number: its place in the whole folder, which stays put while the folder doesn't change."""
    positions = {f.id: n for n, f in enumerate(await rulebooks.files(), 1)}
    result = [(positions[f.id], f) for f in files]
    recent_files.update(result)
    return result


@commands.hybrid_group(name="rpg", description="Search and download RPG rulebooks.", invoke_without_command=True,
                       extras={"private": True, "available": rpg_available, "configured": rpg_configured})
@rpg_enabled()
async def rpg(ctx: commands.Context):
    await ctx.send("Use `/rpg search <anything>` to find rulebooks, then `/rpg download <number or name>` to get one.",
                   ephemeral=True)


@rpg.command(name="search", description="Search the rulebooks by name or folder (e.g. 5e player).")
@rpg_enabled()
@app_commands.describe(query="Words from the name or folder, in any order")
async def rpg_search(ctx: commands.Context, *, query: str):
    await ctx.defer(ephemeral=True)
    try:
        results = await numbered(await rulebooks.search(query))
    except dropbox.DropboxError as error:
        log.warning("RPG search failed: %s", error.log_text)
        await ctx.send(str(error), ephemeral=True)
        return
    if not results:
        await ctx.send(f"No rulebooks match “{discord.utils.escape_markdown(query)}”.", ephemeral=True)
        return
    count = len(results)
    await send_search_pages(ctx, SearchPages(
        results, title=f"🎲 {count} rulebook{'s' if count != 1 else ''} for “{query[:100]}”",
        line=lambda item: file_line(*item), footer="Get one with /rpg download <number or name>.",
        command="/rpg search", author_id=ctx.author.id, per_page=SEARCH_RESULTS_SHOWN, color=discord.Color.dark_green()))


async def find_file(wanted: str) -> dropbox.RpgFile | list[tuple[int, dropbox.RpgFile]]:
    """One file (by autocomplete pick, number or name), or the candidates if the name matches several."""
    files = await rulebooks.files()
    if wanted.startswith("id:"):  # Picked from autocomplete.
        return next((f for f in files if f.id == wanted), None) or []
    if wanted.isdigit():
        number = int(wanted)
        file = recent_files.get(number)
        if file and any(f.id == file.id for f in files):
            return file
        return files[number - 1] if 1 <= number <= len(files) else []
    matches = await rulebooks.search(wanted)
    exact = [f for f in matches if wanted.casefold() in (f.name.casefold(), f.name.rsplit(".", 1)[0].casefold())]
    if len(exact) == 1 or len(matches) == 1:
        return (exact or matches)[0]
    return await numbered(exact or matches)


@rpg.command(name="download", description="Get a download link for a rulebook. Only you will see it.")
@rpg_enabled()
@app_commands.describe(rulebook="Its number from a search, or its name (pick from the list as you type)")
async def rpg_download(ctx: commands.Context, *, rulebook: str):
    await ctx.defer(ephemeral=True)
    try:
        found = await find_file(rulebook.strip())
        if isinstance(found, list):
            if not found:
                await ctx.send(f"No rulebook matches “{discord.utils.escape_markdown(rulebook)}”.", ephemeral=True)
            else:
                lines = "\n".join(file_line(n, f) for n, f in found[:10])
                await ctx.send(f"Several rulebooks match. Download one by its number:\n{lines}", ephemeral=True)
            return
        link = await rulebooks.link(found)
    except dropbox.DropboxError as error:
        log.warning("RPG download failed: %s", error.log_text)
        await ctx.send(str(error), ephemeral=True)
        return

    # Deliberately anonymous: no user, no rulebook.
    log.info("RPG: a download link was sent (%s)", format_size(found.size))
    message = (f"🎲 **{discord.utils.escape_markdown(found.name)}** ({format_size(found.size)})\n"
               f"[Download it]({link})\n-# The link works for {dropbox.LINK_HOURS} hours.")
    if ctx.interaction:
        await ctx.send(message, ephemeral=True)
        return
    try:
        await ctx.author.send(message)
        await ctx.reply("📬 Sent the link to your DMs.")
    except discord.Forbidden:
        await ctx.reply("I couldn't DM you. Allow DMs from server members, or use `/rpg download` instead.")


@rpg_download.autocomplete("rulebook")
async def rulebook_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    if not rpg_available(interaction.guild):
        return []
    try:
        files = await rulebooks.search(current) if current.strip() else await rulebooks.files()
    except dropbox.DropboxError:
        return []
    return [app_commands.Choice(name=(f"{f.name} — {f.folder}" if f.folder else f.name)[:100], value=f.id)
            for f in files[:25]]


def help_extras(command: commands.Command) -> tuple[str, list[tuple[str, str, bool]]]:
    if (command.root_parent or command).name != "rpg":
        return "", []
    p = config.COMMAND_PREFIX
    text = (f"With `/rpg`, search results and links are only shown to you. With `{p}rpg`, search results post in "
            f"the channel and links are sent by DM. Nobody's searches or downloads are logged.\n"
            f"Downloads are links straight from Dropbox, so big rulebooks work; each link lasts "
            f"{dropbox.LINK_HOURS} hours.")
    return "", [("Privacy and downloads", text, False)]


async def setup(bot: commands.Bot):
    bot.add_command(rpg)
