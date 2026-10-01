"""/committee: the committee's funds. Every bribe, expunge and bail pays the committee, and people can spend it.

Money in is the bribes table (so bribes from before this existed count too); money out is committee_spending.
Both are read through db.scope, so shared servers share one committee.
"""

import random
from dataclasses import dataclass
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import config, db
from ktdi.common import NO_PINGS, log, plural

HELP_CATEGORY = "💦 Rap sheet"
ITEM_MAX_LENGTH = 200
LEDGER_SHOWN = 10

# Ideas for /committee propose: (what, price in dollars). The bot works out how many the funds would buy.
PROPOSALS = [
    ("a new set of dice for everyone, because the current ones are clearly cursed", 15),
    ("a fog machine for dramatic entrances", 45),
    ("a framed portrait of the Don", 120),
    ("a plaque commemorating the most unfair spray in history", 60),
    ("an actual spray bottle, for in-person enforcement", 4),
    ("pizza for the next session", 30),
    ("a bigger table, so the maps stop falling off", 250),
    ("a gold-plated d20", 400),
    ("a lawyer, to appeal everyone's rap sheets", 1_500),
    ("a trophy for the Champion Briber", 35),
    ("a soundproof room for when someone rolls a natural 1", 8_000),
    ("bribing a different, bigger committee", 10_000),
    ("a small island, to hold sessions on", 2_500_000),
    ("a tank of fuel for the committee's private jet", 6_000),
    ("enough snacks to survive a five-hour session", 25),
    ("a rubber chicken, for no reason the committee is prepared to explain", 8),
]

FUNDS_LINES = [
    "The committee thanks everyone for their generous, entirely voluntary contributions.",
    "The committee would like to remind everyone that none of this is a bribe.",
    "The committee is open to proposals. And to further contributions.",
    "The committee's accounts are audited regularly, by the committee.",
    "The committee has no comment on where the rest went.",
]

SPEND_LINES = [
    "🧾 The committee has approved {who}'s purchase of **{item}** for **{amount}**.",
    "🧾 {who} has spent **{amount}** of the committee's money on **{item}**. Minutes have been taken.",
    "🧾 Motion carried (probably). {who} put **{amount}** towards **{item}**.",
    "🧾 {who} signed off **{amount}** for **{item}**. The committee will be reviewing this at the next meeting.",
]


@dataclass
class Spend:
    id: int
    guild_id: int
    amount: int
    item: str
    spent_by: int
    created_at: str


def money(amount: int) -> str:
    return f"${amount:,}"


def total_paid_in(guild_id: int) -> int:
    where, params = db.scope(guild_id)
    return db.conn.execute(f"SELECT COALESCE(SUM(total), 0) FROM bribes WHERE {where}", params).fetchone()[0]


def total_spent(guild_id: int, user_id: int | None = None) -> int:
    where, params = db.scope(guild_id)
    if user_id is not None:
        where, params = f"{where} AND spent_by = ?", [*params, user_id]
    return db.conn.execute(f"SELECT COALESCE(SUM(amount), 0) FROM committee_spending WHERE {where}",
                           params).fetchone()[0]


def balance(guild_id: int) -> int:
    return total_paid_in(guild_id) - total_spent(guild_id)


def record_spend(guild_id: int, amount: int, item: str, spent_by: int) -> None:
    db.conn.execute("INSERT INTO committee_spending (guild_id, amount, item, spent_by, created_at) VALUES (?, ?, ?, ?, ?)",
                    (guild_id, amount, item, spent_by, datetime.now(timezone.utc).isoformat()))
    db.conn.commit()


def recent_spending(guild_id: int, limit: int) -> list[Spend]:
    where, params = db.scope(guild_id)
    rows = db.conn.execute(f"SELECT id, guild_id, amount, item, spent_by, created_at FROM committee_spending "
                           f"WHERE {where} ORDER BY id DESC LIMIT ?", (*params, limit)).fetchall()
    return [Spend(*row) for row in rows]


def spend_line(spend: Spend) -> str:
    date = datetime.fromisoformat(spend.created_at).strftime("%d %b %Y")
    return f"**{money(spend.amount)}** on {spend.item}, by <@{spend.spent_by}> ({date})"


def funds_embed(guild_id: int) -> discord.Embed:
    paid_in, spent = total_paid_in(guild_id), total_spent(guild_id)
    embed = discord.Embed(title="🏛️ The committee's funds", description=f"## {money(paid_in - spent)}",
                          color=discord.Color.gold())
    embed.add_field(name="Paid in", value=money(paid_in), inline=True)
    embed.add_field(name="Spent", value=money(spent), inline=True)
    recent = recent_spending(guild_id, 3)
    if recent:
        embed.add_field(name="Recent spending", value="\n".join(spend_line(s) for s in recent), inline=False)
    embed.set_footer(text=random.choice(FUNDS_LINES))
    return embed


def proposal_text(guild_id: int, rng: random.Random = random) -> str:
    funds = balance(guild_id)
    item, price = rng.choice(PROPOSALS)
    if funds <= 0:
        return (f"🏛️ The committee would like to propose **{item}** ({money(price)}), but the committee is broke. "
                "Perhaps someone would like to make a contribution.")
    affordable = funds // price
    if affordable == 0:
        return (f"🏛️ Proposal: **{item}**, at {money(price)}. The committee has {money(funds)}, "
                f"so it's {money(price - funds)} short. More bribes are needed.")
    return (f"🏛️ Proposal: **{item}**, at {money(price)} each. The committee's {money(funds)} would buy "
            f"**{affordable:,}** of them. Debate amongst yourselves; `/committee spend` when you've decided.")


# --- Commands ---
@commands.hybrid_group(name="committee", description="The committee's funds: every bribe, expunge and bail pays in.",
                       invoke_without_command=True)
@commands.guild_only()
async def committee_group(ctx: commands.Context):
    await committee_funds.callback(ctx)


@committee_group.command(name="funds", description="How much the committee has, and what it's spent it on.")
async def committee_funds(ctx: commands.Context):
    await ctx.send(embed=funds_embed(ctx.guild.id), allowed_mentions=NO_PINGS)


@committee_group.command(name="spend", description="Spend the committee's money on something (it goes on the ledger).")
@app_commands.describe(amount="How much to spend", item="What it's being spent on")
async def committee_spend(ctx: commands.Context, amount: commands.Range[int, 1, 1_000_000_000_000], *, item: str):
    item = item.strip()[:ITEM_MAX_LENGTH]  # Shown with NO_PINGS, so an @mention in it pings nobody.
    if not item:
        await ctx.send("Spend it on what? The committee needs it for the minutes.", ephemeral=True)
        return
    funds = balance(ctx.guild.id)
    if amount > funds:
        await ctx.send(f"The committee only has {money(funds)}. It can't spend {money(amount)}, "
                       "however good the cause.", ephemeral=True)
        return
    record_spend(ctx.guild.id, amount, item, ctx.author.id)
    log.info("[%s] %s spent $%s of committee funds", ctx.guild.name, ctx.author, f"{amount:,}")
    line = random.choice(SPEND_LINES).format(who=ctx.author.mention, item=item, amount=money(amount))
    await ctx.send(f"{line}\n-# {money(funds - amount)} left in the committee's funds.", allowed_mentions=NO_PINGS)


@committee_group.command(name="ledger", description="Everything the committee has spent its money on, newest first.")
async def committee_ledger(ctx: commands.Context):
    recent = recent_spending(ctx.guild.id, LEDGER_SHOWN)
    if not recent:
        await ctx.send(f"🧾 The committee hasn't spent anything yet. It has {money(balance(ctx.guild.id))}. "
                       "Try `/committee propose` for ideas.")
        return
    embed = discord.Embed(title="🧾 The committee's ledger", description="\n".join(spend_line(s) for s in recent),
                          color=discord.Color.gold())
    embed.set_footer(text=f"Last {plural(len(recent), 'purchase')}. {money(total_spent(ctx.guild.id))} spent in total, "
                          f"{money(balance(ctx.guild.id))} left.")
    await ctx.send(embed=embed, allowed_mentions=NO_PINGS)


@committee_group.command(name="propose", description="The committee suggests something to spend its money on.")
async def committee_propose(ctx: commands.Context):
    await ctx.send(proposal_text(ctx.guild.id))


def help_extras(command: commands.Command) -> tuple[str, list[tuple[str, str, bool]]]:
    if command.name != "committee":
        return "", []
    p = config.COMMAND_PREFIX
    text = ("• Every `/bribe`, `/expunge` and `/bail` pays the committee, including ones from before the committee "
            "kept accounts.\n"
            "• Anyone can `/committee spend <amount> <item>`, but it can't spend more than it has, and every purchase "
            "goes on the ledger with who signed it off. Spending shows on your rap sheet too.\n"
            "• `/committee propose` suggests something to argue about.\n"
            f"• `{p}committee` on its own shows the funds; `{p}committee spend 50 pizza for the next session` works too.\n"
            "• Shared servers share one committee (see `/settings`).")
    return "", [("How the money works", text, False)]


async def setup(bot: commands.Bot):
    bot.add_command(committee_group)
