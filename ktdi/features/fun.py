"""Spray, whospray, tdoi, loot, linux, blame, bribe, expunge, bail and rap sheets, plus the 💦 reaction and the
Champion Briber role.

"The Don" is the person chosen with /settings whospray_user: /whospray asks them who to spray, and /tdoi
(The Don Ordered It) is someone spraying themselves on the Don's orders.
"""

import random
from collections import defaultdict, deque

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import common, config, db
from ktdi.common import get_member, log, plural

SPRAY_GIF_URL = "https://klipy.com/gifs/spray-bottle-3"
SPRAY_EMOJI = "💦"
LOOT_GIF_URL = "https://klipy.com/gifs/perception-check-tom-cardy"

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

WHOSPRAY_LINES = [
    "{user}, the spray bottle is loaded. Who's getting it?",
    "{user}, who's been a degenerate lately? Name names.",
    "{user}, you've been handed the spray bottle. Choose wisely.",
    "{user}, somebody needs spraying. Who?",
    "{user}, the committee requests your judgement: who gets sprayed?",
    "{user}, point the bottle. Who's first?",
    "{user}, if you could spray one person right now, who would it be?",
    "{user}, the bottle is full and the day is young. Who's getting sprayed?",
    "{user}, justice needs a target. Who?",
    "{user}, pick a degenerate. Any degenerate.",
    "{user}, it's spray o'clock. Who's it going to be?",
    "{user}, who's earned a spritz today?",
]

EXPUNGE_LINES = [
    "💰 {user} slipped the committee **{amount}** and one spray quietly disappeared from their record.",
    "💰 After a generous **{amount}** donation from {user}, the committee has no record of that spray.",
    "💰 {user} paid **{amount}**. What spray? There was never any spray.",
    "💰 **{amount}** changes hands. {user}'s rap sheet is now one spray lighter.",
]

BAIL_LINES = [
    "🔓 {payer} posted **{amount}** bail. One spray is off {target}'s record.",
    "🔓 {payer} paid the committee **{amount}** to clear one of {target}'s sprays. Friendship.",
    "🔓 **{amount}** later, {target} has one less spray, courtesy of {payer}.",
    "🔓 {payer} thought one of {target}'s sprays was unfair, and put **{amount}** where their mouth is.",
]

NO_DON = ("There's no Don on this server yet. Only the people listed in the bot's `WHOSPRAY_ADMIN_IDS` "
          "can choose one, with `/settings whospray_user`.")

# Recent message authors per channel, used to pick someone to blame.
recent_speakers: dict[int, deque[int]] = defaultdict(lambda: deque(maxlen=50))

# Most recent blame per channel: channel_id -> (blamer_id, blamed_id).
last_blame: dict[int, tuple[int, int]] = {}


# --- Sprays and bribes (read through db.scope, so shared servers pool them) ---
def record_spray(guild_id: int, user_id: int) -> int:
    db.conn.execute(
        """
        INSERT INTO sprays (guild_id, user_id, count) VALUES (?, ?, 1)
        ON CONFLICT (guild_id, user_id) DO UPDATE SET count = count + 1
        """,
        (guild_id, user_id),
    )
    db.conn.commit()
    return get_spray_count(guild_id, user_id)


def _scoped_sum(table: str, guild_id: int, user_id: int, column: str = "user_id") -> int:
    where, params = db.scope(guild_id)
    row = db.conn.execute(f"SELECT COALESCE(SUM(count), 0) FROM {table} WHERE {where} AND {column} = ?",
                          (*params, user_id)).fetchone()
    return row[0]


def get_spray_count(guild_id: int, user_id: int) -> int:
    """Sprays on someone's record: every spray, minus the ones expunged (by them) or bailed (by others)."""
    removed = get_expunge_count(guild_id, user_id) + get_bails_received(guild_id, user_id)
    return max(_scoped_sum("sprays", guild_id, user_id) - removed, 0)


def record_bail(guild_id: int, user_id: int, paid_by: int) -> None:
    db.conn.execute(
        """
        INSERT INTO spray_bails (guild_id, user_id, paid_by, count) VALUES (?, ?, ?, 1)
        ON CONFLICT (guild_id, user_id, paid_by) DO UPDATE SET count = count + 1
        """,
        (guild_id, user_id, paid_by),
    )
    db.conn.commit()


def get_bails_received(guild_id: int, user_id: int) -> int:
    return _scoped_sum("spray_bails", guild_id, user_id)


def get_bails_given(guild_id: int, user_id: int) -> int:
    return _scoped_sum("spray_bails", guild_id, user_id, column="paid_by")


def record_expunge(guild_id: int, user_id: int) -> None:
    # Recorded, not deleted: the sprays stay where they were, and the rap sheet shows the net total.
    db.conn.execute(
        """
        INSERT INTO spray_expunges (guild_id, user_id, count) VALUES (?, ?, 1)
        ON CONFLICT (guild_id, user_id) DO UPDATE SET count = count + 1
        """,
        (guild_id, user_id),
    )
    db.conn.commit()


def get_expunge_count(guild_id: int, user_id: int) -> int:
    return _scoped_sum("spray_expunges", guild_id, user_id)


def record_don_order(guild_id: int, user_id: int) -> int:
    db.conn.execute(
        """
        INSERT INTO don_orders (guild_id, user_id, count) VALUES (?, ?, 1)
        ON CONFLICT (guild_id, user_id) DO UPDATE SET count = count + 1
        """,
        (guild_id, user_id),
    )
    db.conn.commit()
    return get_don_order_count(guild_id, user_id)


def get_don_order_count(guild_id: int, user_id: int) -> int:
    return _scoped_sum("don_orders", guild_id, user_id)


def record_bribe(guild_id: int, user_id: int, amount: int) -> None:
    db.conn.execute(
        """
        INSERT INTO bribes (guild_id, user_id, count, total) VALUES (?, ?, 1, ?)
        ON CONFLICT (guild_id, user_id) DO UPDATE SET count = count + 1, total = total + excluded.total
        """,
        (guild_id, user_id, amount),
    )
    db.conn.commit()


def get_bribe_stats(guild_id: int, user_id: int) -> tuple[int, int]:
    where, params = db.scope(guild_id)
    row = db.conn.execute(f"SELECT COALESCE(SUM(count), 0), COALESCE(SUM(total), 0) FROM bribes WHERE {where} AND user_id = ?",
                          (*params, user_id)).fetchone()
    return row[0], row[1]


def get_top_briber(guild_id: int) -> int | None:
    where, params = db.scope(guild_id)
    row = db.conn.execute(f"SELECT user_id FROM bribes WHERE {where} GROUP BY user_id ORDER BY SUM(total) DESC, user_id LIMIT 1",
                          params).fetchone()
    return row[0] if row else None


def get_briber_role_holder(guild_id: int) -> int | None:
    row = db.conn.execute("SELECT user_id FROM briber_role_holders WHERE guild_id = ?", (guild_id,)).fetchone()
    return row[0] if row else None


def set_briber_role_holder(guild_id: int, user_id: int) -> None:
    db.conn.execute(
        "INSERT INTO briber_role_holders (guild_id, user_id) VALUES (?, ?)"
        " ON CONFLICT (guild_id) DO UPDATE SET user_id = excluded.user_id",
        (guild_id, user_id),
    )
    db.conn.commit()


async def update_briber_role(guild: discord.Guild) -> None:
    """Move the briber role to the server's biggest briber. Does nothing if the role or permission is missing."""
    role = discord.utils.get(guild.roles, name=config.BRIBER_ROLE_NAME)
    top_id = get_top_briber(guild.id)
    if role is None or top_id is None:
        return
    previous_id = get_briber_role_holder(guild.id)
    try:
        if previous_id and previous_id != top_id:
            previous = await get_member(guild, previous_id)
            if previous and role in previous.roles:
                await previous.remove_roles(role, reason="No longer the biggest briber")
                log.info("[%s] Took %r from %s", guild.name, config.BRIBER_ROLE_NAME, previous)
        top = await get_member(guild, top_id)
        if top and role not in top.roles:
            await top.add_roles(role, reason="Biggest briber")
            log.info("[%s] Gave %r to %s", guild.name, config.BRIBER_ROLE_NAME, top)
        set_briber_role_holder(guild.id, top_id)
    except discord.HTTPException as error:
        # Usually missing Manage Roles, or the role sits above the bot's own role.
        log.warning("[%s] Couldn't update %r role: %s", guild.name, config.BRIBER_ROLE_NAME, error)


# --- Commands ---
@commands.hybrid_command(name="spray", description="Spray the degenerate.")
@commands.guild_only()
async def spray(ctx: commands.Context, target: discord.Member | None = None):
    if target is None:
        await ctx.send(SPRAY_GIF_URL)
        return
    record_spray(ctx.guild.id, target.id)
    await ctx.send(f"{target.mention} {SPRAY_GIF_URL}")


@commands.hybrid_command(name="whospray", description="Ask the server's chosen sprayer who should get sprayed.")
@commands.guild_only()
async def whospray(ctx: commands.Context):
    asked = db.whospray_user(ctx.guild.id)  # The Don: only ever the person chosen in /settings whospray_user.
    if asked is None:
        await ctx.send(NO_DON, ephemeral=True)
        return
    line = random.choice(WHOSPRAY_LINES).format(user=f"<@{asked}>")
    # Ping only the person being asked.
    await ctx.send(f"{SPRAY_EMOJI} {line}\n-# Deliver it with `/spray @them`.",
                   allowed_mentions=discord.AllowedMentions(users=[discord.Object(id=asked)], everyone=False, roles=False))


@commands.hybrid_command(name="tdoi", description="The Don Ordered It: spray yourself, on the Don's orders.")
@commands.guild_only()
async def tdoi(ctx: commands.Context):
    if db.whospray_user(ctx.guild.id) is None:
        await ctx.send(NO_DON, ephemeral=True)
        return
    record_spray(ctx.guild.id, ctx.author.id)  # It's still a spray...
    times = record_don_order(ctx.guild.id, ctx.author.id)  # ...and one more the Don made them do.
    log.info("[%s] %s sprayed themselves on the Don's orders", ctx.guild.name, ctx.author)
    await ctx.send(f"🤌 The Don ordered it. {ctx.author.mention} sprays themselves.\n{SPRAY_GIF_URL}\n"
                   f"-# That's {plural(times, 'time')} the Don has made them do it.",
                   allowed_mentions=discord.AllowedMentions.none())


@commands.hybrid_command(name="loot", description="Declare that you're looting the body.")
async def loot(ctx: commands.Context):
    await ctx.send(LOOT_GIF_URL)


@commands.hybrid_command(name="rapsheet", description="See someone's sprays, bribes, expunges and bails.")
@commands.guild_only()
async def rapsheet(ctx: commands.Context, user: discord.Member | None = None):
    user = user or ctx.author
    sprays = get_spray_count(ctx.guild.id, user.id)
    bribes, bribe_total = get_bribe_stats(ctx.guild.id, user.id)
    lines = []
    if sprays:
        lines.append(f"Sprayed {plural(sprays, 'time')}.")
    expunged = get_expunge_count(ctx.guild.id, user.id)
    if expunged:
        lines.append(f"🧽 Paid to have {plural(expunged, 'spray')} expunged.")
    bailed = get_bails_received(ctx.guild.id, user.id)
    if bailed:
        lines.append(f"🔓 Bailed out of {plural(bailed, 'spray')} by others.")
    bails_given = get_bails_given(ctx.guild.id, user.id)
    if bails_given:
        lines.append(f"🤝 Bailed others out {plural(bails_given, 'time')}.")
    don_orders = get_don_order_count(ctx.guild.id, user.id)
    if don_orders:
        lines.append(f"🤌 Sprayed themselves on the Don's orders {plural(don_orders, 'time')}.")
    if bribes:
        lines.append(f"Bribed the committee {plural(bribes, 'time')} (${bribe_total:,} total).")
        if get_top_briber(ctx.guild.id) == user.id:
            lines.append("👑 Biggest briber" + (" across the shared servers." if db.is_shared(ctx.guild.id) else " in the server."))
    if not lines:
        await ctx.send(f"📋 {user.display_name} has a clean record. Suspicious.")
        return
    await ctx.send("\n".join([f"📋 **Rap sheet: {user.display_name}**", *lines]))


@commands.hybrid_command(name="blame", description="Blame someone who's been talking recently.")
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


@commands.hybrid_command(name="bribe", description="Blamed? Pay to put the blame back on whoever blamed you.")
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


@commands.hybrid_command(name="expunge", description="Pay the committee to remove a spray from your own rap sheet.")
@commands.guild_only()
async def expunge(ctx: commands.Context, amount: commands.Range[int, 1, 1_000_000_000_000]):
    if get_spray_count(ctx.guild.id, ctx.author.id) == 0:
        await ctx.send("Your record has no sprays on it. Keep your money.", ephemeral=True)
        return
    record_expunge(ctx.guild.id, ctx.author.id)
    record_bribe(ctx.guild.id, ctx.author.id, amount)  # Paying off the committee is still a bribe.
    left = get_spray_count(ctx.guild.id, ctx.author.id)
    log.info("[%s] %s paid $%s to expunge a spray", ctx.guild.name, ctx.author, f"{amount:,}")
    line = random.choice(EXPUNGE_LINES).format(user=ctx.author.mention, amount=f"${amount:,}")
    await ctx.send(f"{line}\n-# {plural(left, 'spray')} left on their record.",
                   allowed_mentions=discord.AllowedMentions.none())
    await update_briber_role(ctx.guild)


@commands.hybrid_command(name="bail", description="Pay the committee to remove a spray from someone else's rap sheet.")
@commands.guild_only()
@app_commands.describe(user="Whose spray to remove", amount="How much bail to post")
async def bail(ctx: commands.Context, user: discord.Member, amount: commands.Range[int, 1, 1_000_000_000_000]):
    if user.id == ctx.author.id:
        await ctx.send("You can't bail yourself out. Use `/expunge` for your own record.", ephemeral=True)
        return
    if get_spray_count(ctx.guild.id, user.id) == 0:
        await ctx.send(f"{user.display_name} has no sprays on their record to bail them out of.", ephemeral=True)
        return
    record_bail(ctx.guild.id, user.id, ctx.author.id)
    record_bribe(ctx.guild.id, ctx.author.id, amount)  # Paying off the committee is still a bribe, by whoever paid.
    left = get_spray_count(ctx.guild.id, user.id)
    log.info("[%s] %s paid $%s bail for user %s", ctx.guild.name, ctx.author, f"{amount:,}", user.id)
    line = random.choice(BAIL_LINES).format(payer=ctx.author.mention, target=user.mention, amount=f"${amount:,}")
    await ctx.send(f"{line}\n-# {plural(left, 'spray')} left on their record.",
                   allowed_mentions=discord.AllowedMentions.none())
    await update_briber_role(ctx.guild)


@commands.hybrid_command(name="linux", description="Ask our resident Linux hater how he's feeling about Linux.")
async def linux(ctx: commands.Context):
    await ctx.send(random.choice(LINUX_LINES).format(user=f"<@{config.LINUX_HATER_ID}>"))


# --- Listeners ---
async def remember_speaker(message: discord.Message):
    if message.guild and not message.author.bot:
        recent_speakers[message.channel.id].append(message.author.id)


async def spray_reaction(payload: discord.RawReactionActionEvent):
    # Reacting 💦 to a message sprays whoever sent it.
    bot = common.bot
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


def main_help_fields() -> list[tuple[str, str]]:
    """Extra lines for the main /help list, for things that aren't commands."""
    return [(f"React {SPRAY_EMOJI}", "Sprays whoever sent the message and adds to their rap sheet.")]


async def setup(bot: commands.Bot):
    for command in (spray, whospray, tdoi, loot, rapsheet, blame, bribe, expunge, bail, linux):
        bot.add_command(command)
    bot.add_listener(remember_speaker, "on_message")
    bot.add_listener(spray_reaction, "on_raw_reaction_add")
