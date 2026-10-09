"""/sprayfutures: bet that someone gets sprayed within a few hours. /sprayrate: today's spray interest rate.

Right, and what's on the line comes off your rap sheet; wrong, and it goes on. What's on the line is your stake times
the hours you bet over, plus the day's spray interest rate (1-20%, picked each day at SPRAY_RATE_TIME and fixed on a
bet when it's placed). Only a spray by someone else counts, so you can't place a bet and then cash it in yourself.
Sprays reach here through fun.after_spray (/spray, 💦, /tdoi); bets that run out are settled by expiry_loop.
Everything's in the database (spray_futures, spray_rates), so open bets and the day's rate survive a restart.
"""

import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from ktdi import common, config, db
from ktdi.common import NO_PINGS, log, plural
from ktdi.features import fun

HELP_CATEGORY = "💦 Rap sheet"
MAX_STAKE = 10
MAX_HOURS = 24
RATE_RANGE = (1, 20)  # The daily spray interest rate, in %.


@dataclass
class Future:
    id: int
    guild_id: int
    channel_id: int
    bettor_id: int
    target_id: int
    amount: int  # What's on the line: stake x hours, plus interest.
    expires_at: datetime


FUTURE_COLUMNS = "id, guild_id, channel_id, bettor_id, target_id, amount, expires_at"


def now() -> datetime:
    return datetime.now(timezone.utc)


# --- The daily spray interest rate ---
def rate_day(moment: datetime) -> date:
    """The day whose SPRAY_RATE_TIME most recently passed (in BOT_TIMEZONE): today's, or before it's set, yesterday's."""
    local = moment.astimezone(config.BOT_TIMEZONE)
    return local.date() if local.time() >= config.SPRAY_RATE_TIME else local.date() - timedelta(days=1)


def next_rate_at(moment: datetime) -> datetime:
    return datetime.combine(rate_day(moment) + timedelta(days=1), config.SPRAY_RATE_TIME, config.BOT_TIMEZONE)


def todays_rate(moment: datetime) -> int:
    """The rate for the day, picked at random (1-20) the first time it's needed after SPRAY_RATE_TIME."""
    day = rate_day(moment).isoformat()
    row = db.conn.execute("SELECT rate FROM spray_rates WHERE day = ?", (day,)).fetchone()
    if row:
        return row[0]
    rate = random.randint(*RATE_RANGE)
    db.conn.execute("INSERT OR IGNORE INTO spray_rates (day, rate, set_at) VALUES (?, ?, ?)",
                    (day, rate, moment.isoformat()))
    db.conn.commit()
    log.info("Spray interest rate for %s: %d%%", day, rate)
    return db.conn.execute("SELECT rate FROM spray_rates WHERE day = ?", (day,)).fetchone()[0]


def amount_at_stake(stake: int, hours: int, rate: int) -> int:
    """stake x hours, plus rate% interest, rounded to the nearest whole spray (halves up)."""
    return (stake * hours * (100 + rate) + 50) // 100


# --- Bets ---
def _future(row) -> Future:
    *rest, expires = row
    return Future(*rest, datetime.fromisoformat(expires))


def open_futures(where: str, params) -> list[Future]:
    rows = db.conn.execute(f"SELECT {FUTURE_COLUMNS} FROM spray_futures WHERE settled_at IS NULL AND {where} "
                           "ORDER BY id", params).fetchall()
    return [_future(row) for row in rows]


def _settle(future: Future, outcome: str, paid: int = 0, sprayed_by: int | None = None) -> None:
    db.conn.execute("UPDATE spray_futures SET settled_at = ?, outcome = ?, paid = ?, sprayed_by = ? WHERE id = ?",
                    (now().isoformat(), outcome, paid, sprayed_by, future.id))
    db.conn.commit()


def sprays(count: int, verb: str) -> str:
    """"1 spray comes", "3 sprays come"; "1 spray goes", "3 sprays go"."""
    singular = {"go": "goes"}.get(verb, verb + "s")
    return f"{plural(count, 'spray')} {singular if count == 1 else verb}"


def settle_on_spray(guild_id: int, target_id: int, sprayer_id: int) -> list[tuple[int, str]]:
    """Pay out open futures on whoever was just sprayed, unless the bettor did the spraying.
    Returns (channel, announcement) for each, to post where the bet was placed."""
    where, params = db.scope(guild_id)
    moment = now()
    messages = []
    for future in open_futures(f"{where} AND target_id = ? AND bettor_id != ?", [*params, target_id, sprayer_id]):
        if future.expires_at <= moment:
            continue  # Too late; the expiry loop will settle it as lost.
        on_record = fun.get_spray_count(future.guild_id, future.bettor_id)
        paid = min(future.amount, on_record)  # Never below a clean record: no banking credit for later.
        _settle(future, "won", paid, sprayer_id)
        log.info("Spray future %d won: %d of %d paid", future.id, paid, future.amount)
        text = f"📈 **Spray future paid out!** <@{sprayer_id}> sprayed <@{target_id}>, so "
        if paid == 0:
            text += f"<@{future.bettor_id}> called it… but their record was already clean, so there's nothing to take off."
        else:
            text += f"{sprays(paid, 'come')} off <@{future.bettor_id}>'s record."
            if paid < future.amount:
                text += f" (They had {future.amount} on the line, but only {paid} to lose.)"
        messages.append((future.channel_id, text))
    return messages


def expire(moment: datetime) -> list[tuple[int, str]]:
    """Settle every open future whose time is up as lost. Returns (channel, announcement) for each."""
    messages = []
    for future in open_futures("expires_at <= ?", [moment.isoformat()]):
        _settle(future, "lost")
        log.info("Spray future %d lost: %d on the line", future.id, future.amount)
        messages.append((future.channel_id,
                         f"📉 **Spray future expired.** Nobody sprayed <@{future.target_id}> in time, so "
                         f"{sprays(future.amount, 'go')} on <@{future.bettor_id}>'s record."))
    return messages


async def announce(messages: list[tuple[int, str]]) -> None:
    for channel_id, text in messages:
        channel = common.bot.get_channel(channel_id)
        if channel is not None:
            try:
                await channel.send(text, allowed_mentions=NO_PINGS)
            except discord.HTTPException:
                pass  # Settled in the database either way.


@tasks.loop(seconds=30)
async def expiry_loop():
    await announce(expire(now()))


@expiry_loop.before_loop
async def before_expiry_loop():
    await common.bot.wait_until_ready()


def ensure_expiry_loop() -> None:
    """Run the expiry check while there are open bets (only on the real, ready bot; never in tests)."""
    is_ready = getattr(common.bot, "is_ready", None)
    if is_ready and is_ready() and not expiry_loop.is_running():
        expiry_loop.start()


# --- Commands ---
@commands.hybrid_command(name="sprayfutures",
                         description="Bet someone gets sprayed in time: right, sprays off your record; wrong, sprays on.")
@commands.guild_only()
@app_commands.describe(user="Who you reckon is getting sprayed",
                       stake=f"Sprays to stake per hour (1 to {MAX_STAKE}; 1 if you leave it out)",
                       hours=f"How long they've got (1 to {MAX_HOURS}; 1 if you leave it out). Multiplies the stake.")
async def sprayfutures(ctx: commands.Context, user: discord.Member, stake: commands.Range[int, 1, MAX_STAKE] = 1,
                       hours: commands.Range[int, 1, MAX_HOURS] = 1):
    if user.id == ctx.author.id:
        await ctx.send("You can't take out futures on yourself. Nice try.", ephemeral=True)
        return
    if user.bot:
        await ctx.send("Bots don't get sprayed. Pick a degenerate.", ephemeral=True)
        return
    existing = open_futures("guild_id = ? AND bettor_id = ? AND target_id = ?", [ctx.guild.id, ctx.author.id, user.id])
    if existing:
        await ctx.send(f"You've already got a future on {user.display_name}; it settles "
                       f"<t:{int(existing[0].expires_at.timestamp())}:R>.", ephemeral=True)
        return
    moment = now()
    rate = todays_rate(moment)  # Fixed now, so you know what you're betting.
    amount = amount_at_stake(stake, hours, rate)
    expires = moment + timedelta(hours=hours)
    db.conn.execute("INSERT INTO spray_futures (guild_id, channel_id, bettor_id, target_id, stake, hours, rate, amount, "
                    "created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (ctx.guild.id, ctx.channel.id, ctx.author.id, user.id, stake, hours, rate, amount,
                     moment.isoformat(), expires.isoformat()))
    db.conn.commit()
    log.info("[%s] %s took out a spray future on user %s (%d x %dh at %d%% = %d)", ctx.guild.name, ctx.author,
             user.id, stake, hours, rate, amount)
    when = int(expires.timestamp())
    sum_text = f"{plural(stake, 'spray')} × {plural(hours, 'hour')}" if hours > 1 else plural(stake, "spray")
    await ctx.send(f"📈 {ctx.author.mention} is betting {user.mention} gets sprayed by <t:{when}:t> (<t:{when}:R>): "
                   f"{sum_text}, plus today's {rate}% spray interest = **{plural(amount, 'spray')}** on the line.\n"
                   f"-# If someone else sprays them before then, {sprays(amount, 'come')} off {ctx.author.mention}'s "
                   f"record. If not, {sprays(amount, 'go')} on. Spraying them yourself "
                   f"doesn't count.", allowed_mentions=NO_PINGS)
    ensure_expiry_loop()


@commands.hybrid_command(name="sprayrate", description="Today's spray interest rate, for /sprayfutures.")
async def sprayrate(ctx: commands.Context):
    moment = now()
    rate = todays_rate(moment)
    await ctx.send(f"📊 Today's spray interest rate is **{rate}%**. Every spray future placed today pays (or costs) "
                   f"{rate}% on top.\n-# The next rate is set <t:{int(next_rate_at(moment).timestamp())}:R>.")


def help_extras(command: commands.Command) -> tuple[str, list[tuple[str, str, bool]]]:
    if command.name not in ("sprayfutures", "sprayrate"):
        return "", []
    text = (f"• Bet that someone gets sprayed within `hours` (1 to {MAX_HOURS}, default 1), staking 1 to {MAX_STAKE} "
            "sprays (default 1) per hour.\n"
            "• On the line: stake × hours, plus the day's spray interest rate (`/sprayrate`, 1-20%, new each day), "
            "rounded. The rate's fixed when you bet. E.g. 2 sprays × 3 hours at 15% = 7.\n"
            "• The moment someone **other than you** sprays them (`/spray`, a 💦 reaction, even `/tdoi`), you win: "
            "that much comes off your rap sheet (never below a clean record).\n"
            "• If the time runs out, you lose, and that much goes on your rap sheet.\n"
            "• No betting on yourself, and one open bet per person you're betting on.")
    return "", [("How it works", text, False)]


async def setup(bot: commands.Bot):
    bot.add_command(sprayfutures)
    bot.add_command(sprayrate)
    if open_futures("1 = 1", []):  # Bets left open over a restart still need settling.
        expiry_loop.start()


async def teardown(bot: commands.Bot):
    expiry_loop.cancel()
