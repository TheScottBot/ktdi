"""/insurance: spray insurance, sold by the committee. Corrupt, but it genuinely works.

$1,000 buys a policy (the premium goes to the committee, like a bribe) that forgives every spray while it's in force:
the spray still happens, and still pays out spray futures, but it doesn't go on your rap sheet. A policy lasts
2:00-9:59, set by the committee's two clocks (ktdi/lib/insurance.py): the microwave decides claims, the car clock is
the countdown customers see, and they disagree by up to 20%. Nobody announces when the real cover runs out. The clocks
are deliberately predictable from your ID and the minute you buy; working out a good minute is the game.

Sprays reach here through fun.take_spray (/spray, 💦, /tdoi). Policies and claims are in the database.
"""

import random
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import db
from ktdi.common import NO_PINGS, log, plural
from ktdi.features import fun
from ktdi.lib import insurance as clocks

HELP_CATEGORY = "💦 Rap sheet"
PREMIUM = 1_000

SALES_LINES = [
    "🛡️ {user} has bought spray insurance for **{premium}**. The committee thanks them for their business.",
    "🛡️ {user} paid **{premium}** for spray insurance. The committee has filed the paperwork somewhere.",
    "🛡️ {user} is now insured against sprays, for **{premium}**. Terms and conditions are in the microwave.",
    "🛡️ Policy sold: {user}, **{premium}**. The committee is legally obliged to call this a premium.",
]
# Excuses for the clocks disagreeing. Picked at random, whatever the clocks are actually doing.
CUSTOMER_SERVICE = [
    "Yeah, we've got a few different clocks in the office.",
    "Oh, that one's always been a bit fast.",
    "We use the microwave for insurance.",
    "The car clock's always been a bit funny.",
    "Well, the car wasn't here yesterday.",
    "Someone unplugged the microwave.",
    "Yeah, we know they're different.",
    "I think Dave normally sorts that.",
    "We've been meaning to get that looked at.",
    "Well, we're not a clock company.",
    "Oh yeah, someone else mentioned that.",
]


def now() -> datetime:
    return datetime.now(timezone.utc)


def money(amount: int) -> str:
    return f"${amount:,}"


def latest_policy(guild_id: int, user_id: int):
    """Their policy in force (the newest, even if it's run out): (id, microwave expiry, car expiry), or None."""
    where, params = db.scope(guild_id)
    row = db.conn.execute(f"SELECT id, microwave_expires_at, car_expires_at FROM insurance_policies WHERE {where} "
                          "AND user_id = ? ORDER BY id DESC LIMIT 1", (*params, user_id)).fetchone()
    if row is None:
        return None
    return row[0], datetime.fromisoformat(row[1]), datetime.fromisoformat(row[2])


def buy(guild_id: int, user_id: int, moment: datetime) -> tuple[datetime, bool]:
    """Sell a policy at this moment. Returns (the car clock's expiry, whether it replaced one still showing time)."""
    previous = latest_policy(guild_id, user_id)
    replaced = previous is not None and previous[2] > moment
    microwave, car = clocks.clocks(user_id, moment.minute)
    car_expires = moment + timedelta(seconds=car)
    db.conn.execute("INSERT INTO insurance_policies (guild_id, user_id, premium, bought_at, microwave_expires_at, "
                    "car_expires_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (guild_id, user_id, PREMIUM, moment.isoformat(),
                     (moment + timedelta(seconds=microwave)).isoformat(), car_expires.isoformat()))
    db.conn.commit()
    fun.record_bribe(guild_id, user_id, PREMIUM)  # Premiums go to the committee, like every other payment.
    return car_expires, replaced


def adjudicate(guild_id: int, user_id: int, sprayer_id: int) -> tuple[bool, str]:
    """Is this spray covered? If so the claim's recorded. Returns (covered, a line to add to the spray's message)."""
    policy = latest_policy(guild_id, user_id)
    moment = now()
    if policy is None:
        return False, ""
    policy_id, microwave_expires, car_expires = policy
    if moment < microwave_expires:
        db.conn.execute("INSERT INTO insurance_claims (guild_id, policy_id, user_id, sprayed_by, claimed_at) "
                        "VALUES (?, ?, ?, ?, ?)", (guild_id, policy_id, user_id, sprayer_id, moment.isoformat()))
        db.conn.commit()
        log.info("Insurance claim on policy %d approved", policy_id)
        return True, f"-# 🛡️ <@{user_id}> is insured. Claim approved: this one's not going on their record."
    if moment < car_expires:  # The countdown says they're covered. The microwave says otherwise.
        when = int(car_expires.timestamp())
        return False, (f"-# 🛡️ <@{user_id}>'s policy has run out. Their countdown says <t:{when}:R>, but the "
                       "committee goes by the microwave.")
    return False, ""


def claim_count(guild_id: int, user_id: int) -> int:
    where, params = db.scope(guild_id)
    return db.conn.execute(f"SELECT COUNT(*) FROM insurance_claims WHERE {where} AND user_id = ?",
                           (*params, user_id)).fetchone()[0]


# --- Commands ---
@commands.hybrid_group(name="insurance", description="$1,000 to the committee and sprays don't count. For a while.",
                       invoke_without_command=True)
@commands.guild_only()
async def insurance_group(ctx: commands.Context):
    await insurance_status.callback(ctx)


@insurance_group.command(name="buy", description="Buy spray insurance: $1,000 to the committee, a few minutes' cover.")
async def insurance_buy(ctx: commands.Context):
    car_expires, replaced = buy(ctx.guild.id, ctx.author.id, now())
    log.info("[%s] %s bought spray insurance", ctx.guild.name, ctx.author)
    when = int(car_expires.timestamp())
    line = random.choice(SALES_LINES).format(user=ctx.author.mention, premium=money(PREMIUM))
    text = f"{line}\n⏱️ Covered until <t:{when}:T> (<t:{when}:R>)."
    if replaced:
        text += "\n-# Their old policy has been cancelled. No refunds."
    await ctx.send(text, allowed_mentions=NO_PINGS)
    await fun.update_briber_role(ctx.guild)


@insurance_group.command(name="status", description="When someone's spray insurance runs out (according to the car).")
@app_commands.describe(user="Whose policy to check (leave empty for yours)")
async def insurance_status(ctx: commands.Context, user: discord.Member | None = None):
    user = user or ctx.author
    policy = latest_policy(ctx.guild.id, user.id)
    covered = claim_count(ctx.guild.id, user.id)
    claims = f"\n-# {plural(covered, 'spray')} covered so far." if covered else ""
    if policy is None:
        await ctx.send(f"🛡️ {user.display_name} has never bought spray insurance. `/insurance buy` is "
                       f"{money(PREMIUM)}.{claims}")
        return
    when = int(policy[2].timestamp())
    if policy[2] > now():
        await ctx.send(f"🛡️ {user.display_name}'s policy runs out <t:{when}:R> (<t:{when}:T>).{claims}")
    else:
        await ctx.send(f"🛡️ {user.display_name}'s policy ran out <t:{when}:R>. `/insurance buy` for another."
                       f"{claims}")


@insurance_group.command(name="complain", description="Ask the committee why the clocks don't match.")
async def insurance_complain(ctx: commands.Context):
    await ctx.send(f"📞 {random.choice(CUSTOMER_SERVICE)}")


def help_extras(command: commands.Command) -> tuple[str, list[tuple[str, str, bool]]]:
    if command.name != "insurance":
        return "", []
    text = (f"• `/insurance buy`: {money(PREMIUM)} to the committee (it counts as a bribe) for 2:00 to 9:59 of cover. "
            "Buying again replaces your policy, with no refund.\n"
            "• While you're covered, sprays still happen (and still pay out spray futures) but don't go on your rap "
            "sheet.\n"
            "• The countdown you're shown is the car clock. Claims go by the microwave. They're up to 20% apart, "
            "either can run out first, and nobody tells you when the real cover ends.\n"
            "• Neither clock is random: they come from your user ID and the minute (UTC) you buy. The sums are in "
            "`ktdi/lib/insurance.py`, if you want to find a good minute.\n"
            "• `/insurance complain` if the clocks bother you.")
    return "", [("The small print", text, False)]


async def setup(bot: commands.Bot):
    bot.add_command(insurance_group)
