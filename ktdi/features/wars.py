"""/wars: the KTDI War Archives. A burst of sprays, /bad and /badbonk in a channel is quietly recognised as a conflict,
and once everyone's calmed down the committee publishes an official historical report on it, out of nowhere.

Every act of hostility (spraying or telling off someone else; spraying yourself doesn't count) is logged in
`hostilities`. When CONFLICT_ACTS of them land in one channel within CONFLICT_WINDOW, a conflict has started; nothing's
said. Each act in that channel after that joins it, until nobody's done anything for CEASEFIRE. Then ceasefire_loop
ends it and classifies it: a war if WAR_ATTACKERS or more people attacked, or a special military operation if it was
one person on a spree (someone firing back turns an operation into a war). It's named from what happened (how long,
when, which weapon, who suffered) and the report is posted there. Conflicts stay in their channel: separate stupidity
in two places is two wars, even on servers that share state. Acts reach here through fun.after_spray and fun.tell_off.
Sprays weren't timestamped before this, so the archives only go back to when it was added.
"""

import random
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from ktdi import common, config, db
from ktdi.common import NO_PINGS, log, plural

HELP_CATEGORY = "🎲 Fun"
CONFLICT_ACTS = 4  # This many acts of hostility...
CONFLICT_WINDOW = timedelta(minutes=5)  # ...in one channel within this long is a conflict.
WAR_ATTACKERS = 2  # A war if this many people attacked; one person alone is a special military operation.
CEASEFIRE = timedelta(minutes=10)  # It's over once nobody's done anything for this long.
DOMINANT_SHARE = 0.6  # A war fought mostly with one weapon is named after it.
HISTORY_SHOWN = 10
WEAPONS = ["spray", "bad", "badbonk"]

ORDINALS = ["First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth", "Ninth", "Tenth", "Eleventh",
            "Twelfth", "Thirteenth", "Fourteenth", "Fifteenth", "Sixteenth", "Seventeenth", "Eighteenth", "Nineteenth",
            "Twentieth"]
ONES = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve",
        "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

# A war's title comes from how it went. These are for wars fought mostly with one weapon...
WEAPON_TITLES = {
    "bad": ["The {ordinal} Great Badening", "The Great Badening of {year}", "The War to End All Bads"],
    "badbonk": ["The {ordinal} Great Bonkening", "The Great Bonkening of {year}", "The War to End All Bonks"],
    "spray": ["The {ordinal} Great Soaking", "The Battle of the Wet Trousers", "The War to End All Sprays"],
}
# ...these from when it was, how long, how many, and who suffered...
FACT_TITLES = [
    "The {minutes_words}-Minute War",
    "The Incident at {time}",
    "The {weekday} Atrocity",
    "The War of {acts_words} Poor Decisions",
    "The Siege of {persecuted}'s Dignity",
]
EVENING_TITLES = ["The {weekday} Night Massacre"]
LONE_VICTIM_TITLES = ["The Persecution of {persecuted}"]  # The most persecuted never fired back.
# ...and these fit any war.
GENERIC_TITLES = [
    "The Battle of Absolutely Nothing",
    "The War of Mutual Disappointment",
    "The {ordinal} Conflict of Unspecified Origin",
]
# One person on a spree is never a war. These are for special military operations, by what was used...
OPERATION_WEAPON_TITLES = {
    "bad": ["The Badening of {persecuted}", "The {ordinal} Unilateral Badening"],
    "badbonk": ["The Bonking of {persecuted}", "The {ordinal} Unilateral Bonkening"],
    "spray": ["The Soaking of {persecuted}", "The {ordinal} Unilateral Soaking"],
}
# ...and by who, when and to whom.
OPERATION_TITLES = [
    "{aggressor}'s Special Military Operation",
    "The {ordinal} Special Military Operation",
    "The Unprovoked Incursion at {time}",
    "The {weekday} Incursion",
    "The {minutes_words}-Minute Special Military Operation",
    "The {aggressor} Doctrine",
]
OPERATION_EVENING_TITLES = ["The {weekday} Night Raid"]
ONE_TARGET_TITLES = ["The Annexation of {persecuted}", "The Liberation of {persecuted}'s Dignity"]
CAUSES = [
    "Unclear. Historians believe {first} may have started it.",
    "Disputed. {first} maintains it was self-defence.",
    "{first} fired first, and has been insufferable about it since.",
    "Lost to history. {first} was seen nearby.",
    "A misunderstanding, almost certainly {first}'s.",
]
OUTCOMES = [
    "An uneasy peace was established when everyone stopped talking.",
    "Everyone got bored.",
    "Both sides claimed victory.",
    "The committee declared a ceasefire, then went to bed.",
    "Hostilities ended when someone put the kettle on.",
    "A stalemate. Nobody learned anything.",
]
SIGNIFICANCE = [
    "None whatsoever.",
    "Negligible.",
    "Hotly disputed by the one historian who cares.",
    "To be taught in schools (it won't be).",
    "Commemorated annually by nobody.",
]
OPERATION_CAUSES = [
    "{first} acted alone. Nobody knows why.",
    "{first} cited \"historical grievances\".",
    "{first} insists it was a peacekeeping mission.",
    "{first} was \"just testing something\".",
    "Pre-emptive, according to {first}. Against what remains unclear.",
]
OPERATION_OUTCOMES = [
    "The operation concluded when its commander got bored.",
    "Objectives were declared achieved. Nobody knows what they were.",
    "The targets did not fire back. The committee is unsure whether that's dignity or fear.",
    "The commander withdrew to \"regroup\", and hasn't been seen since.",
]
FOOTER = "Officially recognised as a war by the committee. No objections will be entertained."
OPERATION_FOOTER = ("Officially recognised as a special military operation by the committee. It is not a war, and "
                    "must not be called one.")


def now() -> datetime:
    return datetime.now(timezone.utc)


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value)


def number_words(n: int) -> str:
    """23 -> "Twenty-Three". 100 and up stays as digits."""
    if n < 20:
        return ONES[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return TENS[tens] + (f"-{ONES[ones]}" if ones else "")
    return f"{n:,}"


def ordinal(n: int) -> str:
    return ORDINALS[n - 1] if n <= len(ORDINALS) else f"{n:,}th"


async def member_name(guild_id: int, user_id: int) -> str:
    """Their name in the server, for titles (which can't show mentions). Asks Discord if it's not cached."""
    get_guild = getattr(common.bot, "get_guild", None)
    guild = get_guild(guild_id) if get_guild else None
    member = await common.get_member(guild, user_id) if guild else None
    return member.display_name if member else "Someone"


# --- Recording ---
def open_war(channel_id: int):
    """(id, last act) for the conflict going on in this channel, or None. Ongoing ones are a secret."""
    # The newest: if the ceasefire loop's behind, an old one can still be open (it'll be reported), and a new one
    # started after it is the one that's going on.
    row = db.conn.execute("SELECT id, last_act_at FROM wars WHERE channel_id = ? AND ended_at IS NULL "
                          "ORDER BY id DESC LIMIT 1", (channel_id,)).fetchone()
    return (row[0], _time(row[1])) if row else None


def record(guild_id: int, channel_id: int, actor_id: int, target_id: int, weapon: str, covered: bool = False) -> None:
    """Log an act of hostility, quietly starting a conflict if it's tipped this channel into one."""
    if actor_id == target_id:
        return  # Spraying yourself (/tdoi) is a cry for help, not an act of war.
    moment = now()
    war = open_war(channel_id)
    if war and moment - war[1] > CEASEFIRE:  # Over, but the loop hasn't got to it yet: this is separate.
        war = None
    db.conn.execute("INSERT INTO hostilities (guild_id, channel_id, actor_id, target_id, weapon, at, war_id, covered) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (guild_id, channel_id, actor_id, target_id, weapon,
                                                        moment.isoformat(), war[0] if war else None, int(covered)))
    if war:
        db.conn.execute("UPDATE wars SET last_act_at = ? WHERE id = ?", (moment.isoformat(), war[0]))
        db.conn.commit()
        return
    recent = db.conn.execute("SELECT id, actor_id, at FROM hostilities WHERE channel_id = ? AND war_id IS NULL "
                             "AND at > ? ORDER BY at, id",
                             (channel_id, (moment - CONFLICT_WINDOW).isoformat())).fetchall()
    if len(recent) >= CONFLICT_ACTS:
        war_id = db.conn.execute("INSERT INTO wars (guild_id, channel_id, title, started_at, last_act_at) "
                                 "VALUES (?, ?, '', ?, ?)",  # Named once it's over, from how it went.
                                 (guild_id, channel_id, recent[0][2], moment.isoformat())).lastrowid
        db.conn.execute(f"UPDATE hostilities SET war_id = ? WHERE id IN ({', '.join('?' * len(recent))})",
                        (war_id, *[act_id for act_id, _, _ in recent]))
        log.info("A conflict started in channel %s (%d)", channel_id, war_id)
        ensure_ceasefire_loop()
    db.conn.commit()


async def hostility(guild_id: int, channel_id: int, actor_id: int, target_id: int, weapon: str,
                    covered: bool = False) -> None:
    """Every spray, /bad and /badbonk at someone comes here (from fun). Nothing's said: it's all reported after."""
    record(guild_id, channel_id, actor_id, target_id, weapon, covered)


# --- The record ---
@dataclass
class War:
    id: int
    guild_id: int
    channel_id: int
    title: str
    started: datetime
    ended: datetime
    acts: list[tuple[int, int, str, bool]]  # (actor, target, weapon, covered by insurance), in order

    @property
    def is_war(self) -> bool:
        """Otherwise it's a special military operation: one person, on their own."""
        return len(self.attackers) >= WAR_ATTACKERS

    @property
    def kind(self) -> str:
        return "war" if self.is_war else "special military operation"

    @property
    def attackers(self) -> Counter:
        return Counter(actor for actor, *_ in self.acts)

    @property
    def targets(self) -> Counter:
        return Counter(target for _, target, *_ in self.acts)

    @property
    def weapons(self) -> Counter:
        return Counter(weapon for _, _, weapon, _ in self.acts)

    @property
    def belligerents(self) -> set[int]:
        return set(self.attackers) | set(self.targets)

    @property
    def casualties(self) -> int:
        """Hits that went on someone's record (insurance paid out on the rest)."""
        return sum(not covered for *_, covered in self.acts)

    @property
    def minutes(self) -> int:
        return max(1, round((self.ended - self.started).total_seconds() / 60))

    @property
    def persecuted(self) -> tuple[int, int]:
        return self.targets.most_common(1)[0]

    @property
    def aggressor(self) -> tuple[int, int]:
        return self.attackers.most_common(1)[0]

    def rng(self, purpose: str) -> random.Random:
        """Seeded by the war, so its report reads the same every time it's looked up."""
        return random.Random(f"war:{self.id}:{purpose}")


def get_war(war_id: int) -> War | None:
    row = db.conn.execute("SELECT id, guild_id, channel_id, title, started_at, COALESCE(ended_at, last_act_at) "
                          "FROM wars WHERE id = ?", (war_id,)).fetchone()
    if row is None:
        return None
    acts = db.conn.execute("SELECT actor_id, target_id, weapon, covered FROM hostilities WHERE war_id = ? "
                           "ORDER BY at, id", (war_id,)).fetchall()
    return War(*row[:4], _time(row[4]), _time(row[5]), [(a, t, w, bool(c)) for a, t, w, c in acts])


def war_title(war: War, number: int, names: dict[str, str]) -> str:
    """Gloriously disproportionate, and drawn from what actually happened."""
    titles, weights = zip(*title_options(war, number, names))
    return war.rng("title").choices(titles, weights)[0]


def title_options(war: War, number: int, names: dict[str, str]) -> list[tuple[str, int]]:
    """Every title that fits, with how likely each is: what made it stand out weighs most. `number` is which war (or
    operation) of its kind it is here; `names` has the "persecuted" and "aggressor" names."""
    start = war.started.astimezone(config.BOT_TIMEZONE)
    persecuted_id, _ = war.persecuted
    facts = {"ordinal": ordinal(number), "year": start.year, "minutes_words": number_words(war.minutes),
             "time": start.strftime("%H:%M"), "weekday": start.strftime("%A"),
             "acts_words": number_words(len(war.acts)), **names}
    weapon, used = war.weapons.most_common(1)[0]
    dominant = used / len(war.acts) >= DOMINANT_SHARE
    evening = start.hour >= 18 or start.hour < 4
    if war.is_war:
        weighted = [(title, 1) for title in GENERIC_TITLES] + [(title, 2) for title in FACT_TITLES]
        if dominant:
            weighted += [(title, 4) for title in WEAPON_TITLES[weapon]]
        if evening:
            weighted += [(title, 2) for title in EVENING_TITLES]
        if persecuted_id not in war.attackers:
            weighted += [(title, 3) for title in LONE_VICTIM_TITLES]
    else:
        weighted = [(title, 2) for title in OPERATION_TITLES]
        if dominant:
            weighted += [(title, 3) for title in OPERATION_WEAPON_TITLES[weapon]]
        if evening:
            weighted += [(title, 2) for title in OPERATION_EVENING_TITLES]
        if len(war.targets) == 1:
            weighted += [(title, 3) for title in ONE_TARGET_TITLES]
    return [(title.format(**facts), weight) for title, weight in weighted]


def report(war: War, number: int) -> discord.Embed:
    """The committee's official historical record of a war or special military operation. `number` is its place in
    the archives."""
    start, end = war.started.astimezone(config.BOT_TIMEZONE), war.ended.astimezone(config.BOT_TIMEZONE)
    when = (f"{start.day} {start.strftime('%B %Y')} · {start.strftime('%H:%M')}–{end.strftime('%H:%M')} · "
            f"{plural(war.minutes, 'minute')}")
    embed = discord.Embed(title=war.title[:256], description=f"{when}\nClassified as: **{war.kind}**",
                          color=discord.Color.dark_gold() if war.is_war else discord.Color.dark_grey())
    embed.set_author(name="KTDI Historical Records Office")
    embed.add_field(name="Hostilities", value=str(len(war.acts)))
    embed.add_field(name="Belligerents", value=str(len(war.belligerents)))
    embed.add_field(name="Casualties", value=str(war.casualties))
    aggressor, attacks = war.aggressor
    persecuted, hits = war.persecuted
    causes = CAUSES if war.is_war else OPERATION_CAUSES
    lines = [f"**Cause of conflict:** {war.rng('cause').choice(causes).format(first=f'<@{war.acts[0][0]}>')}",
             f"**Most aggressive combatant:** <@{aggressor}> — {plural(attacks, 'incident')}" if war.is_war
             else f"**Commanding officer:** <@{aggressor}> — {plural(attacks, 'incident')}",
             f"**Most persecuted:** <@{persecuted}> — {plural(hits, 'incident')}"]
    pacifists = [u for u in war.targets if u not in war.attackers]
    if pacifists:
        lines.append("**Never fired back:** " + ", ".join(f"<@{u}>" for u in pacifists))
    lines.append("**Arsenal:** " + ", ".join(plural(war.weapons[w], w) for w in WEAPONS if war.weapons[w]))
    if war.casualties < len(war.acts):
        lines.append(f"**Insurance claims:** {len(war.acts) - war.casualties}")
    lines += [f"**Outcome:** {war.rng('outcome').choice(OUTCOMES if war.is_war else OPERATION_OUTCOMES)}",
              f"**Historical significance:** {war.rng('significance').choice(SIGNIFICANCE)}"]
    embed.add_field(name="​", value="\n".join(lines)[:1024], inline=False)
    embed.set_footer(text=f"{FOOTER if war.is_war else OPERATION_FOOTER}\nNumber {number} in the archives.")
    return embed


def archived(guild_id: int) -> list[int]:
    """This server's finished wars and operations, oldest first (1 is the first). Ongoing ones aren't in yet."""
    return [row[0] for row in db.conn.execute("SELECT id FROM wars WHERE guild_id = ? AND ended_at IS NOT NULL "
                                              "ORDER BY id", (guild_id,))]


async def ceasefires(moment: datetime) -> list[tuple[int, discord.Embed]]:
    """End every conflict that's gone quiet, classify it and name it. Returns (channel, report) for each."""
    rows = db.conn.execute("SELECT id FROM wars WHERE ended_at IS NULL AND last_act_at <= ? ORDER BY id",
                           ((moment - CEASEFIRE).isoformat(),)).fetchall()
    reports = []
    for (war_id,) in rows:
        db.conn.execute("UPDATE wars SET ended_at = last_act_at WHERE id = ?", (war_id,))
        war = get_war(war_id)
        earlier = archived(war.guild_id)
        of_its_kind = sum(get_war(other).is_war == war.is_war for other in earlier if other <= war_id)
        names = {"persecuted": await member_name(war.guild_id, war.persecuted[0]),
                 "aggressor": await member_name(war.guild_id, war.aggressor[0])}
        war.title = war_title(war, of_its_kind, names)
        db.conn.execute("UPDATE wars SET title = ? WHERE id = ?", (war.title, war_id))
        db.conn.commit()
        log.info("Conflict %d is over (%s): %r", war_id, war.kind, war.title)
        reports.append((war.channel_id, report(war, earlier.index(war_id) + 1)))
    return reports


@tasks.loop(seconds=60)
async def ceasefire_loop():
    for channel_id, embed in await ceasefires(now()):
        channel = common.bot.get_channel(channel_id)
        if channel is not None:
            try:
                await channel.send("📜 **The committee has reviewed recent events in this channel.**", embed=embed,
                                   allowed_mentions=NO_PINGS)
            except discord.HTTPException:
                pass  # It's in the archives either way.
    if not db.conn.execute("SELECT 1 FROM wars WHERE ended_at IS NULL").fetchone():
        ceasefire_loop.stop()


@ceasefire_loop.before_loop
async def before_ceasefire_loop():
    await common.bot.wait_until_ready()


def ensure_ceasefire_loop() -> None:
    """Watch for ceasefires while there's fighting (only on the real, ready bot; never in tests)."""
    is_ready = getattr(common.bot, "is_ready", None)
    if is_ready and is_ready() and not ceasefire_loop.is_running():
        ceasefire_loop.start()


# --- /wars ---
@commands.hybrid_command(name="wars", description="The KTDI War Archives: every war and operation here, or one in full.")
@commands.guild_only()
@app_commands.describe(number="Which one, in order (leave empty for the list)")
async def wars(ctx: commands.Context, number: int | None = None):
    war_ids = archived(ctx.guild.id)
    if number is None:
        if not war_ids:
            await ctx.send("📜 The archives are empty. Peace, as far as the committee knows.")
            return
        lines = []
        for n in range(len(war_ids), max(len(war_ids) - HISTORY_SHOWN, 0), -1):
            war = get_war(war_ids[n - 1])
            start = war.started.astimezone(config.BOT_TIMEZONE)
            acts = len(war.acts)
            lines.append(f"`{n}.` {'⚔️' if war.is_war else '🪖'} **{war.title}**, "
                         f"{start.day} {start.strftime('%b %Y')} "
                         f"({acts} {'hostility' if acts == 1 else 'hostilities'})")
        embed = discord.Embed(title="📜 The KTDI War Archives", description="\n".join(lines),
                              color=discord.Color.dark_gold())
        embed.set_footer(text="⚔️ war · 🪖 special military operation. /wars <number> for the full record.")
        await ctx.send(embed=embed)
        return
    if not 1 <= number <= len(war_ids):
        await ctx.send(f"There's no number {number} in the archives. Only {len(war_ids)} so far.",
                       ephemeral=True)
        return
    await ctx.send(embed=report(get_war(war_ids[number - 1]), number), allowed_mentions=NO_PINGS)


def help_extras(command: commands.Command) -> tuple[str, list[tuple[str, str, bool]]]:
    if command.name != "wars":
        return "", []
    text = (f"• {CONFLICT_ACTS} or more sprays, `/bad`s and `/badbonk`s in one channel within "
            f"{int(CONFLICT_WINDOW.total_seconds() // 60)} minutes is a war if {WAR_ATTACKERS}+ people are at it, or a "
            "special military operation if it's one person on a spree (until someone fires back). Nobody's told "
            "while it's going on.\n"
            f"• Once nobody's done anything for {int(CEASEFIRE.total_seconds() // 60)} minutes it's over: the "
            "committee names it after what happened and publishes the official report in that channel.\n"
            "• Each channel's wars are its own. Spraying yourself doesn't count.")
    return "", [("Rules of engagement", text, False)]


async def setup(bot: commands.Bot):
    bot.add_command(wars)
    if db.conn.execute("SELECT 1 FROM wars WHERE ended_at IS NULL").fetchone():  # Fighting left going over a restart.
        ceasefire_loop.start()


async def teardown(bot: commands.Bot):
    ceasefire_loop.cancel()
