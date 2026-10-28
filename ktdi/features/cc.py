"""Conservative calls (/cc, !cc): our own book of the things a very conservative person would call us (a queer group)
when he can't bring himself to use our names, and the innocent things that sound exactly like it ("People haven't
been taking their tarps in"). Ours to add to; it starts empty. Folklore, not a quote: nobody's named on one, not
who said it or who added it (added_by is kept only so they can delete it).

The quotes' storage (ktdi/features/quotes.py) in a table of its own, cc_quotes, so the gag has its own numbers and
never mixes with the real quotes. One slash command with options (no subcommands: they'd each take a row in Discord's
menu), and the typed one reads its own words: !cc, !cc 3, !cc add ..., a reply with !cc, !cc search ..., !cc last,
!cc delete 3.
"""

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import config, db
from ktdi.common import NO_PINGS, Reply, log, respond, send_reply
from ktdi.features import quotes
from ktdi.features.quotes import ANONYMOUS, QUOTE_MAX_LENGTH, Quote

HELP_CATEGORY = "💬 Quotes"
TABLE = "cc_quotes"
LIST_MAX = 10
PAGE_SIZE = 10  # The whole book, a page at a time (◀ ▶)
COLOUR = discord.Color.from_rgb(170, 60, 200)


INTRO = "A very conservative person may call a member of the queer community:"


def embed(call: Quote) -> discord.Embed:
    result = discord.Embed(title="🧓 Conservative calls", description=f"{INTRO}\n## “{call.text}”", color=COLOUR)
    result.set_footer(text=f"#{call.id}")
    return result


def add_call(guild: discord.Guild, channel_id: int | None, author: discord.abc.User, text: str | None) -> Reply:
    text = (text or "").strip()
    if not text:
        return Reply("Add what they'd call us: `!cc add Doesn't take their tarps in`.", private=True)
    if len(text) > QUOTE_MAX_LENGTH:
        return Reply(f"Too long: {QUOTE_MAX_LENGTH} characters at most.", private=True)
    number = quotes.add_quote(guild.id, ANONYMOUS, text, None, author.id, channel_id, table=TABLE)
    log.info("[%s] %s added conservative call #%d", guild.name, author, number)
    return Reply(f"🧓 Added #{number}.", embed(quotes.get_quote(guild.id, number, table=TABLE)))


def show(guild: discord.Guild, number: int | None = None) -> Reply:
    call = quotes.get_quote(guild.id, number, table=TABLE) if number else quotes.random_quote(guild.id, table=TABLE)
    if call is None:
        return Reply(f"There's no #{number}." if number else "Nothing yet. Add the first: `/cc add:...` or "
                     "`!cc add ...`, or reply to a message with `!cc`.", private=True)
    return Reply(embed=embed(call))


def listing(guild: discord.Guild, search: str | None = None) -> Reply:
    calls = (quotes.search_quotes(guild.id, search.strip(), LIST_MAX, table=TABLE) if search
             else quotes.recent_quotes(guild.id, LIST_MAX, table=TABLE))
    if not calls:
        return Reply(f"Nothing mentions “{discord.utils.escape_markdown(search)}”." if search else
                     "Nothing yet.", private=True)
    title = f"🔎 Conservative calls mentioning “{search[:80]}”" if search else "🧓 The latest conservative calls"
    lines = [f"`#{c.id}` “{c.text if len(c.text) <= 90 else c.text[:90].rstrip() + '…'}”" for c in calls]
    return Reply(embed=discord.Embed(title=title, description="\n".join(lines), color=COLOUR))


def page_of(guild_id: int, page: int) -> tuple[list[Quote], int, int]:
    """One page of the book, oldest first: (its calls, the page it is, how many pages). Out of range is the nearest."""
    where, params = db.scope(guild_id)
    total = db.conn.execute(f"SELECT COUNT(*) FROM {TABLE} WHERE {where}", params).fetchone()[0]
    pages = max(1, -(-total // PAGE_SIZE))
    page = min(max(1, page), pages)
    rows = db.conn.execute(f"SELECT {quotes.QUOTE_COLUMNS} FROM {TABLE} WHERE {where} ORDER BY id LIMIT ? OFFSET ?",
                           (*params, PAGE_SIZE, (page - 1) * PAGE_SIZE)).fetchall()
    return [Quote(*row) for row in rows], page, pages


def page_embed(guild_id: int, page: int) -> tuple[discord.Embed | None, "Pages | None"]:
    calls, page, pages = page_of(guild_id, page)
    if not calls:
        return None, None
    lines = [f"`#{c.id}` “{c.text if len(c.text) <= 90 else c.text[:90].rstrip() + '…'}”" for c in calls]
    result = discord.Embed(title="🧓 Conservative calls", description="\n".join(lines), color=COLOUR)
    result.set_footer(text=f"Page {page} of {pages}")
    return result, (Pages(guild_id, page, pages) if pages > 1 else None)


class Pages(discord.ui.View):
    """◀ ▶ under a page of the book: anyone can turn them, for ten minutes."""

    def __init__(self, guild_id: int, page: int, pages: int):
        super().__init__(timeout=600)
        self.guild_id, self.page = guild_id, page
        self.back.disabled, self.forward.disabled = page <= 1, page >= pages

    async def turn(self, interaction: discord.Interaction, page: int):
        embed_, view = page_embed(self.guild_id, page)
        if embed_ is None:
            await interaction.response.edit_message(content="Nothing left in it.", embed=None, view=None)
            return
        await interaction.response.edit_message(embed=embed_, view=view)

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.turn(interaction, self.page - 1)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary)
    async def forward(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.turn(interaction, self.page + 1)


def remove(guild: discord.Guild, member: discord.Member, number: int) -> Reply:
    call = quotes.get_quote(guild.id, number, table=TABLE)
    if call is None:
        return Reply(f"There's no #{number}.", private=True)
    if member.id != call.added_by and not member.guild_permissions.manage_messages:
        return Reply(f"Only whoever added #{number}, or a moderator, can delete it.", private=True)
    quotes.delete_quote(guild.id, number, table=TABLE)
    log.info("[%s] %s deleted conservative call #%d", guild.name, member, number)
    return Reply(f"🗑️ Deleted #{number}.")


# --- Typed: !cc reads its own words ---
@commands.command(name="cc", description="Conservative calls: what they call us when they won't use our names.")
@commands.guild_only()
async def cc_prefix(ctx: commands.Context, *, args: str = ""):
    """Conservative calls: our book of the things a very conservative person calls us when he can't bring himself to
    use our names ("One of the alphabet people"), and the perfectly innocent things that sound exactly like it
    ("People haven't been taking their tarps in"). It starts empty: it's ours to fill. It's folklore, not quotes:
    nobody's named on them, neither who said it nor who added it.

    • `/cc` on its own: a random one. `number:3` shows #3; `search:tarps` finds them; `page:1` lists them all, ten
    a page, with ◀ ▶ to turn; `delete:3` deletes #3 (whoever added it, or a mod).
    • **Add one:** `/cc add:Doesn't take their tarps in`, or reply to a message with `!cc` to save its words (just
    the words: not who wrote them).
    • Typed: `!cc`, `!cc 3`, `!cc add Doesn't take their tarps in`, `!cc search tarps`, `!cc list` (or `!cc list 2`),
    `!cc last`, `!cc delete 3`.

    Its own numbers, separate from `/quote`."""
    words = args.split(maxsplit=1)
    first, rest = (words[0].lower(), words[1] if len(words) > 1 else "") if words else ("", "")
    try:
        replied = await quotes.replied_message(ctx)
    except discord.HTTPException:
        replied = None
    if replied and first != "add":
        reply = add_call(ctx.guild, ctx.channel.id, ctx.author, args or replied.content)
    elif first == "add":
        reply = add_call(ctx.guild, ctx.channel.id, ctx.author, rest)
    elif first == "search" and rest:
        reply = listing(ctx.guild, rest)
    elif first == "last":
        reply = listing(ctx.guild)
    elif first in ("list", "page") and (not rest or rest.strip().isdigit()):
        found, view = page_embed(ctx.guild.id, int(rest) if rest.strip() else 1)
        if found is None:
            await send_reply(ctx, show(ctx.guild))  # Its "nothing yet"
        else:
            await ctx.send(embed=found, view=view, allowed_mentions=NO_PINGS)
        return
    elif first == "delete" and rest.strip().isdigit():
        reply = remove(ctx.guild, ctx.author, int(rest))
    elif first.isdigit() and not rest:
        reply = show(ctx.guild, int(first))
    elif not args:
        reply = show(ctx.guild)
    else:
        p = config.COMMAND_PREFIX
        reply = Reply(f"Try `{p}cc`, `{p}cc 3`, `{p}cc add <what they'd call us>`, "
                      f"`{p}cc search <text>`, `{p}cc list`, `{p}cc last` or `{p}cc delete 3`.")
    await send_reply(ctx, reply)


# --- Slash: one command, with options ---
@app_commands.command(name="cc", description="Conservative calls: what they call us when they won't use our names.")
@app_commands.guild_only()
@app_commands.describe(add="Add one: what they'd call us", number="Show this one",
                       search="Find ones mentioning this", page="List them, ten a page (1 is the first)",
                       delete="Delete this one")
async def cc_slash(interaction: discord.Interaction, add: app_commands.Range[str, 1, QUOTE_MAX_LENGTH] | None = None,
                   number: int | None = None, search: str | None = None,
                   page: app_commands.Range[int, 1] | None = None, delete: int | None = None):
    if add:
        reply = add_call(interaction.guild, interaction.channel_id, interaction.user, add)
    elif delete is not None:
        reply = remove(interaction.guild, interaction.user, delete)
    elif search:
        reply = listing(interaction.guild, search)
    elif page is not None:
        found, view = page_embed(interaction.guild.id, page)
        if found is not None:
            await interaction.response.send_message(embed=found, view=view or discord.utils.MISSING,
                                                    allowed_mentions=NO_PINGS)
            return
        reply = show(interaction.guild)  # Its "nothing yet"
    else:
        reply = show(interaction.guild, number)
    await respond(interaction, reply)


async def setup(bot: commands.Bot):
    bot.add_command(cc_prefix)
    bot.tree.add_command(cc_slash)
