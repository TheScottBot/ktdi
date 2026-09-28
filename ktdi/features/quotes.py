"""Quotes. Ways in: /quote add, !quote @user text, replying to a message with !quote [@user],
or right-click a message > Apps > Save quote."""

import re
from dataclasses import dataclass
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import config, db
from ktdi.common import NO_PINGS, Reply, log, respond, send_reply

ANONYMOUS = 0  # user_id for quotes that aren't credited to anyone.
QUOTE_MAX_LENGTH = 1000
QUOTE_CONTEXT_MAX_LENGTH = 200
QUOTE_LIST_MAX = 15
QUOTE_COLUMNS = "id, guild_id, user_id, text, context, added_by, channel_id, message_id, created_at"
MENTION_AT_START_RE = re.compile(r"^\s*<@!?(\d+)>\s*(.*)$", re.DOTALL)


@dataclass
class Quote:
    id: int
    guild_id: int
    user_id: int
    text: str
    context: str | None
    added_by: int
    channel_id: int | None
    message_id: int | None
    created_at: str


# --- Storage. Reads take the asking server's ID and see whatever its shared state allows. Quote IDs are unique
# across all servers, so #12 means the same quote everywhere it's visible. ---
def add_quote(guild_id: int, user_id: int, text: str, context: str | None, added_by: int,
              channel_id: int | None = None, message_id: int | None = None) -> int:
    cursor = db.conn.execute(
        "INSERT INTO quotes (guild_id, user_id, text, context, added_by, channel_id, message_id, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (guild_id, user_id, text, context, added_by, channel_id, message_id,
         datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )
    db.conn.commit()
    return cursor.lastrowid


def get_quote(guild_id: int, quote_id: int) -> Quote | None:
    where, params = db.scope(guild_id)
    row = db.conn.execute(f"SELECT {QUOTE_COLUMNS} FROM quotes WHERE {where} AND id = ?", (*params, quote_id)).fetchone()
    return Quote(*row) if row else None


def quote_for_message(guild_id: int, message_id: int) -> Quote | None:
    where, params = db.scope(guild_id)
    row = db.conn.execute(f"SELECT {QUOTE_COLUMNS} FROM quotes WHERE {where} AND message_id = ?",
                          (*params, message_id)).fetchone()
    return Quote(*row) if row else None


def random_quote(guild_id: int, user_id: int | None = None) -> Quote | None:
    where, params = db.scope(guild_id)
    if user_id is not None:
        where, params = f"{where} AND user_id = ?", [*params, user_id]
    row = db.conn.execute(f"SELECT {QUOTE_COLUMNS} FROM quotes WHERE {where} ORDER BY RANDOM() LIMIT 1", params).fetchone()
    return Quote(*row) if row else None


def search_quotes(guild_id: int, text: str, limit: int = 10) -> list[Quote]:
    where, params = db.scope(guild_id)
    pattern = "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    rows = db.conn.execute(
        f"SELECT {QUOTE_COLUMNS} FROM quotes WHERE {where} AND (text LIKE ? ESCAPE '\\' OR context LIKE ? ESCAPE '\\')"
        " ORDER BY id DESC LIMIT ?",
        (*params, pattern, pattern, limit),
    ).fetchall()
    return [Quote(*row) for row in rows]


def recent_quotes(guild_id: int, limit: int, user_id: int | None = None) -> list[Quote]:
    where, params = db.scope(guild_id)
    if user_id is not None:
        where, params = f"{where} AND user_id = ?", [*params, user_id]
    rows = db.conn.execute(f"SELECT {QUOTE_COLUMNS} FROM quotes WHERE {where} ORDER BY id DESC LIMIT ?",
                           (*params, limit)).fetchall()
    return [Quote(*row) for row in rows]


def anonymise_quote(guild_id: int, quote_id: int) -> None:
    # The message link goes too, since it would show who wrote it.
    where, params = db.scope(guild_id)
    db.conn.execute(f"UPDATE quotes SET user_id = ?, channel_id = NULL, message_id = NULL WHERE {where} AND id = ?",
                    (ANONYMOUS, *params, quote_id))
    db.conn.commit()


def claim_quote(guild_id: int, quote_id: int, user_id: int) -> None:
    where, params = db.scope(guild_id)
    db.conn.execute(f"UPDATE quotes SET user_id = ? WHERE {where} AND id = ? AND user_id = ?",
                    (user_id, *params, quote_id, ANONYMOUS))
    db.conn.commit()


def delete_quote(guild_id: int, quote_id: int) -> None:
    where, params = db.scope(guild_id)
    db.conn.execute(f"DELETE FROM quotes WHERE {where} AND id = ?", (*params, quote_id))
    db.conn.commit()


# --- Display ---
def said_by(quote: Quote) -> str:
    return "*Anonymous*" if quote.user_id == ANONYMOUS else f"<@{quote.user_id}>"


def quote_embed(quote: Quote) -> discord.Embed:
    description = f"“{quote.text}”\n— {said_by(quote)}"
    if quote.context:
        description += f"\n*{quote.context}*"
    if quote.message_id and quote.channel_id:
        description += f"\n[Original message](https://discord.com/channels/{quote.guild_id}/{quote.channel_id}/{quote.message_id})"
    embed = discord.Embed(description=description, color=discord.Color.gold(),
                          timestamp=datetime.fromisoformat(quote.created_at))
    embed.set_footer(text=f"Quote #{quote.id}")
    return embed


def quote_line(quote: Quote, length: int = 80) -> str:
    """One-line summary for lists: #12 “text…” — @user · date."""
    text = quote.text if len(quote.text) <= length else quote.text[:length].rstrip() + "…"
    when = int(datetime.fromisoformat(quote.created_at).timestamp())
    return f"`#{quote.id}` “{text}” — {said_by(quote)} · <t:{when}:d>"


def split_context(text: str) -> tuple[str, str | None]:
    """'I cast fireball -- on myself' -> ('I cast fireball', 'on myself')."""
    if " -- " in f" {text} ":
        quote_text, _, context = f" {text} ".partition(" -- ")
        return quote_text.strip(), context.strip() or None
    return text.strip(), None


# --- Actions, shared by the prefix, slash and right-click versions ---
def save_quote(guild: discord.Guild, channel_id: int | None, added_by: discord.abc.User, speaker_id: int,
               text: str | None, context: str | None, source: discord.Message | None = None) -> Reply:
    """Save a quote. speaker_id=ANONYMOUS saves it uncredited (and without a link to the original message)."""
    text = (text or "").strip()
    context = (context or "").strip() or None
    if not text:
        if source:
            return Reply("That message has no text, so type the quote in with `/quote add`.", private=True)
        return Reply("There's nothing to quote. Add what was said.", private=True)
    if len(text) > QUOTE_MAX_LENGTH:
        return Reply(f"That's a bit long for a quote (max {QUOTE_MAX_LENGTH} characters).", private=True)
    if context and len(context) > QUOTE_CONTEXT_MAX_LENGTH:
        return Reply(f"The context is too long (max {QUOTE_CONTEXT_MAX_LENGTH} characters).", private=True)
    anonymous = speaker_id == ANONYMOUS
    if anonymous:
        channel_id = source = None  # A link to the original message would give away who said it.
    if source:
        existing = quote_for_message(guild.id, source.id)
        if existing and existing.text == text and existing.user_id == speaker_id:
            return Reply(f"That's already saved as quote #{existing.id}.", private=True)
    quote_id = add_quote(guild.id, speaker_id, text, context, added_by.id, channel_id, source.id if source else None)
    log.info("[%s] %s saved %squote #%d", guild.name, added_by, "an anonymous " if anonymous else "", quote_id)
    label = "anonymous quote" if anonymous else "quote"
    return Reply(f"📌 Saved {label} #{quote_id}.", quote_embed(get_quote(guild.id, quote_id)))


def dissociate_quote(guild: discord.Guild, member: discord.Member, number: int) -> Reply:
    quote = get_quote(guild.id, number)
    if quote is None:
        return Reply(f"There's no quote #{number}.", private=True)
    if quote.user_id == ANONYMOUS:
        return Reply(f"Quote #{number} is already anonymous.", private=True)
    if member.id not in (quote.added_by, quote.user_id) and not member.guild_permissions.manage_messages:
        return Reply(f"Only the person quoted, whoever saved it, or a moderator can make quote #{number} anonymous.",
                     private=True)
    anonymise_quote(guild.id, number)
    # Deliberately doesn't log who asked: that alone would reveal whose quote it was.
    log.info("[%s] Quote #%d was made anonymous", guild.name, number)
    return Reply(f"🕶️ Quote #{number} is now anonymous.", quote_embed(get_quote(guild.id, number)))


def claim(guild: discord.Guild, member: discord.Member, number: int) -> Reply:
    """Put your own name on an anonymous quote. Only ever yourself, so nobody can undo someone's dissociate."""
    quote = get_quote(guild.id, number)
    if quote is None:
        return Reply(f"There's no quote #{number}.", private=True)
    if quote.user_id == member.id:
        return Reply(f"Quote #{number} is already yours.", private=True)
    if quote.user_id != ANONYMOUS:
        return Reply(f"Quote #{number} isn't anonymous, so it can't be claimed.", private=True)
    claim_quote(guild.id, number, member.id)
    log.info("[%s] %s claimed quote #%d", guild.name, member, number)
    return Reply(f"🙋 {member.mention} claimed quote #{number}.", quote_embed(get_quote(guild.id, number)))


def show_random_quote(guild: discord.Guild, user: discord.abc.User | None = None) -> Reply:
    quote = random_quote(guild.id, user.id if user else None)
    if quote is None:
        if user:
            return Reply(f"No quotes from {user.display_name} yet.", private=True)
        return Reply("No quotes saved yet. Reply to a message with `!quote`, or use `/quote add`.", private=True)
    return Reply(embed=quote_embed(quote))


def show_quote(guild: discord.Guild, number: int) -> Reply:
    quote = get_quote(guild.id, number)
    return Reply(embed=quote_embed(quote)) if quote else Reply(f"There's no quote #{number}.", private=True)


def remove_quote(guild: discord.Guild, member: discord.Member, number: int) -> Reply:
    quote = get_quote(guild.id, number)
    if quote is None:
        return Reply(f"There's no quote #{number}.", private=True)
    if member.id not in (quote.added_by, quote.user_id) and not member.guild_permissions.manage_messages:
        return Reply(f"Only whoever saved quote #{number}, the person quoted, or a moderator can delete it.", private=True)
    delete_quote(guild.id, number)
    log.info("[%s] %s deleted quote #%d", guild.name, member, number)
    return Reply(f"🗑️ Deleted quote #{number}.")


def last_quotes(guild: discord.Guild, count: int, user: discord.abc.User | None = None) -> Reply:
    count = max(1, min(count, QUOTE_LIST_MAX))
    quotes = recent_quotes(guild.id, count, user.id if user else None)
    if not quotes:
        return show_random_quote(guild, user)  # Same "no quotes yet" message.
    who = f" from {user.display_name}" if user else ""
    embed = discord.Embed(title=f"🗒️ Last {len(quotes)} quote{'s' if len(quotes) != 1 else ''}{who}",
                          description="\n".join(quote_line(q, 120) for q in quotes), color=discord.Color.gold())
    embed.set_footer(text="Show one in full with /quote show <number>.")
    return Reply(embed=embed)


def find_quotes(guild: discord.Guild, text: str) -> Reply:
    results = search_quotes(guild.id, text.strip())
    if not results:
        return Reply(f"No quotes mention “{discord.utils.escape_markdown(text)}”.", private=True)
    lines = [quote_line(q) for q in results]
    embed = discord.Embed(title=f"🔎 Quotes mentioning “{text[:100]}”", description="\n".join(lines),
                          color=discord.Color.gold())
    embed.set_footer(text="Show one with /quote show <number>." + (" Showing the 10 newest." if len(results) == 10 else ""))
    return Reply(embed=embed)


async def replied_message(ctx: commands.Context) -> discord.Message | None:
    reference = ctx.message.reference
    if reference is None or reference.message_id is None:
        return None
    if isinstance(reference.resolved, discord.Message):
        return reference.resolved
    return await ctx.channel.fetch_message(reference.message_id)


# --- Prefix version: !quote handles replies and "@user text" itself, plus the same subcommands as /quote ---
@commands.group(name="quote", description="Save and replay the things people say.", invoke_without_command=True)
@commands.guild_only()
async def quote_prefix(ctx: commands.Context, *, args: str = ""):
    p = config.COMMAND_PREFIX
    match = MENTION_AT_START_RE.match(args)
    speaker = int(match.group(1)) if match else None
    text = (match.group(2) if match else args).strip()
    try:
        replied = await replied_message(ctx)
    except discord.HTTPException:
        await ctx.send("I couldn't read the message you replied to. I need the Read Message History permission here.")
        return

    if replied:
        # "!quote" or "!quote @Dave" as a reply saves that message; any text typed replaces its wording.
        quote_text, context = split_context(text)
        reply = save_quote(ctx.guild, ctx.channel.id, ctx.author, speaker or replied.author.id,
                           quote_text or replied.content, context, replied)
    elif speaker is None and text.isdigit():
        reply = show_quote(ctx.guild, int(text))
    elif text and speaker is None:
        reply = Reply(f"Who said it? Use `{p}quote @someone what they said`, reply to their message "
                      f"with `{p}quote`, or use `{p}quote anon what was said`.")
    elif text:
        quote_text, context = split_context(text)
        reply = save_quote(ctx.guild, ctx.channel.id, ctx.author, speaker, quote_text, context)
    else:
        # "!quote" or "!quote @Dave" on its own: a random quote.
        user = discord.utils.get(ctx.message.mentions, id=speaker) if speaker else None
        reply = show_random_quote(ctx.guild, user)
    await send_reply(ctx, reply)


# Prefix only: in /quote add you just leave the user empty. Marked so /help shows it as !quote anon.
@quote_prefix.command(name="anon", aliases=["anonymous"], description="Save a quote without crediting anyone.",
                      extras={"prefix_only": True})
async def quote_prefix_anon(ctx: commands.Context, *, text: str = ""):
    p = config.COMMAND_PREFIX
    try:
        replied = await replied_message(ctx)
    except discord.HTTPException:
        replied = None
    quote_text, context = split_context(text)
    if not quote_text and replied is None:
        await send_reply(ctx, Reply(f"What was said? `{p}quote anon what was said`, "
                                    f"or reply to a message with `{p}quote anon`."))
        return
    await send_reply(ctx, save_quote(ctx.guild, ctx.channel.id, ctx.author, ANONYMOUS,
                                     quote_text or replied.content, context))


@quote_prefix.command(name="claim", aliases=["update"], description="Put your own name on an anonymous quote.")
async def quote_prefix_claim(ctx: commands.Context, number: int):
    await send_reply(ctx, claim(ctx.guild, ctx.author, number))


@quote_prefix.command(name="dissociate", aliases=["anonymise", "anonymize"],
                      description="Remove the name from a quote, keeping the quote (the person quoted, whoever saved it, or a mod).")
async def quote_prefix_dissociate(ctx: commands.Context, number: int):
    await send_reply(ctx, dissociate_quote(ctx.guild, ctx.author, number))


@quote_prefix.command(name="add", usage="<text> [user] [context]",  # Shown in /help, which describes the slash version.
                      description="Save something someone said. Leave out the user for an anonymous quote.")
async def quote_prefix_add(ctx: commands.Context, user: discord.Member | None = None, *, text: str = ""):
    # "!quote add @Dave text", "!quote add anon text" and "!quote add text" (anonymous) all work.
    if user is None:
        first, _, rest = text.partition(" ")
        if first.lower() in ("anon", "anonymous"):
            text = rest
    quote_text, context = split_context(text)
    await send_reply(ctx, save_quote(ctx.guild, ctx.channel.id, ctx.author, user.id if user else ANONYMOUS,
                                     quote_text, context))


@quote_prefix.command(name="random", description="A random quote, optionally from one person.")
async def quote_prefix_random(ctx: commands.Context, user: discord.Member | None = None):
    await send_reply(ctx, show_random_quote(ctx.guild, user))


@quote_prefix.command(name="last", description=f"The most recent quotes (default 5, max {QUOTE_LIST_MAX}), optionally from one person.")
async def quote_prefix_last(ctx: commands.Context, count: int | None = 5, user: discord.Member | None = None):
    await send_reply(ctx, last_quotes(ctx.guild, count or 5, user))


@quote_prefix.command(name="show", description="Show a quote by its number.")
async def quote_prefix_show(ctx: commands.Context, number: int):
    await send_reply(ctx, show_quote(ctx.guild, number))


@quote_prefix.command(name="search", description="Find quotes containing some text.")
async def quote_prefix_search(ctx: commands.Context, *, text: str):
    await send_reply(ctx, find_quotes(ctx.guild, text))


@quote_prefix.command(name="delete", description="Delete a quote (whoever saved it, the person quoted, or a mod).")
async def quote_prefix_delete(ctx: commands.Context, number: int):
    await send_reply(ctx, remove_quote(ctx.guild, ctx.author, number))


# --- Slash version ---
quote_slash = app_commands.Group(name="quote", description="Save and replay the things people say.", guild_only=True)


@quote_slash.command(name="add", description="Save something someone said (great for things said in voice).")
@app_commands.describe(text="What they said", user="Who said it. Leave empty to save it anonymously",
                       context="Optional: what was going on at the time")
async def quote_slash_add(interaction: discord.Interaction, text: app_commands.Range[str, 1, QUOTE_MAX_LENGTH],
                          user: discord.Member | None = None,
                          context: app_commands.Range[str, 1, QUOTE_CONTEXT_MAX_LENGTH] | None = None):
    speaker = user.id if user else ANONYMOUS
    await respond(interaction, save_quote(interaction.guild, interaction.channel_id, interaction.user, speaker, text, context))


@quote_slash.command(name="dissociate",
                     description="Remove the name from a quote, keeping the quote (the person quoted, whoever saved it, or a mod).")
async def quote_slash_dissociate(interaction: discord.Interaction, number: int):
    await respond(interaction, dissociate_quote(interaction.guild, interaction.user, number))


@quote_slash.command(name="claim", description="Put your own name on an anonymous quote.")
@app_commands.describe(number="The anonymous quote's number")
async def quote_slash_claim(interaction: discord.Interaction, number: int):
    await respond(interaction, claim(interaction.guild, interaction.user, number))


@quote_slash.command(name="random", description="A random quote, optionally from one person.")
async def quote_slash_random(interaction: discord.Interaction, user: discord.Member | None = None):
    await respond(interaction, show_random_quote(interaction.guild, user))


@quote_slash.command(name="last", description="The most recent quotes, optionally from one person.")
@app_commands.describe(count=f"How many (default 5, max {QUOTE_LIST_MAX})", user="Only quotes from this person")
async def quote_slash_last(interaction: discord.Interaction,
                           count: app_commands.Range[int, 1, QUOTE_LIST_MAX] = 5, user: discord.Member | None = None):
    await respond(interaction, last_quotes(interaction.guild, count, user))


@quote_slash.command(name="show", description="Show a quote by its number.")
async def quote_slash_show(interaction: discord.Interaction, number: int):
    await respond(interaction, show_quote(interaction.guild, number))


@quote_slash.command(name="search", description="Find quotes containing some text.")
async def quote_slash_search(interaction: discord.Interaction, text: str):
    await respond(interaction, find_quotes(interaction.guild, text))


@quote_slash.command(name="delete", description="Delete a quote (whoever saved it, the person quoted, or a mod).")
async def quote_slash_delete(interaction: discord.Interaction, number: int):
    await respond(interaction, remove_quote(interaction.guild, interaction.user, number))


# --- Right-click a message > Apps > Save quote ---
class SaveQuoteModal(discord.ui.Modal, title="Save quote"):
    """Lets you fix the wording and pick who said it."""

    def __init__(self, source: discord.Message):
        super().__init__()
        self.source = source
        self.quote_text = discord.ui.TextInput(style=discord.TextStyle.paragraph, max_length=QUOTE_MAX_LENGTH,
                                               default=source.content[:QUOTE_MAX_LENGTH] or None)
        self.said_by = discord.ui.UserSelect(default_values=[discord.Object(id=source.author.id)],
                                             required=False, min_values=0)
        self.context = discord.ui.TextInput(required=False, max_length=QUOTE_CONTEXT_MAX_LENGTH,
                                            placeholder="e.g. mid-fight, right after rolling a nat 1")
        self.add_item(discord.ui.Label(text="Quote", component=self.quote_text))
        self.add_item(discord.ui.Label(text="Who said it?", component=self.said_by,
                                       description="Change it if someone typed out what another person said, "
                                                   "or clear it to save anonymously."))
        self.add_item(discord.ui.Label(text="Context (optional)", component=self.context))

    async def on_submit(self, interaction: discord.Interaction):
        speaker = self.said_by.values[0].id if self.said_by.values else ANONYMOUS  # Cleared picker = anonymous.
        await respond(interaction, save_quote(interaction.guild, self.source.channel.id, interaction.user, speaker,
                                              self.quote_text.value, self.context.value, self.source))


@app_commands.context_menu(name="Save quote")
@app_commands.guild_only()
async def save_quote_menu(interaction: discord.Interaction, message: discord.Message):
    await interaction.response.send_modal(SaveQuoteModal(message))


def help_extras(command: commands.Command) -> tuple[str, list[tuple[str, str, bool]]]:
    parent = command.parent.name if command.parent else None
    if not (command.name == "quote" or (parent == "quote" and command.name in ("add", "anon"))):
        return "", []
    p = config.COMMAND_PREFIX
    text = (
        f"• **Reply** to a message with `{p}quote` to save it, or `{p}quote @someone` "
        "to credit someone else (handy when a person types out what someone said in voice).\n"
        f"• **Type it:** `{p}quote @someone what they said`. Add ` -- context` on the end for context.\n"
        "• **Right-click a message** → Apps → **Save quote** to edit the wording and pick who said it "
        "(clear the picker to save it anonymously).\n"
        f"• **Anonymous:** leave `user` empty in `/quote add`, or use `{p}quote anon` "
        "(which also works as a reply). "
        "`/quote dissociate <#>` takes the name off an existing quote, and `/quote claim <#>` "
        "lets you put your own name back on an anonymous one.\n"
        f"• `{p}quote` on its own gives a random quote; `{p}quote 12` shows quote #12."
    )
    return "", [("More ways to save a quote", text, False)]


async def setup(bot: commands.Bot):
    bot.add_command(quote_prefix)
    bot.tree.add_command(quote_slash)
    bot.tree.add_command(save_quote_menu)
