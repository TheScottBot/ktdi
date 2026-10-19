"""/bread: How well do you 🍞? (As they'd say in Somerset, "how well do you be read": how well-read are you?)
A question a day from the old books.

Once a day, at the time a server picks (/bread setup here [time]), the daily bread is posted: yesterday's bake
(its answer, who got it right, the book's own words and a link, and the week's top bakers), then today's question,
with four buttons. People answer whenever they like: a button answers privately, once, and nobody sees what anyone
picked until the next day's post. /bread today shows today's question again, for whoever missed it.

The questions are in ktdi/lib/bread.json, built by ktdi/tools/bread_build.py from the old books (and
scenarios written by hand, checked against their passages). A server gets every question once before any comes round
again; a kind of question (lost words, Grose's slang, Bierce, the etiquette manuals...) is picked first, then one of
its questions, so the biggest books don't crowd out the rest. Scores follow the shared state like everything else (a
shared server sees every shared server's answers); streaks count the server's own questions. Everyone who gets the
day's question right gets a 🍞: they're counted on the rap sheet (breads), and the table gives your loaf (LOAVES).

The buttons outlast restarts: each one's custom_id is "bread:<bake id>:<choice>", read back by Answer (a
DynamicItem the bot registers in setup), so a day-old post still takes answers until the next one closes it.
"""

import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import daily, db, oldbooks
from ktdi.common import NO_PINGS, log

HELP_CATEGORY = "📚 Words & wisdom"
DATA = Path(__file__).resolve().parent.parent / "lib" / "bread.json"
QUESTIONS: dict[str, dict] = {q["id"]: q for q in json.loads(DATA.read_text(encoding="utf-8"))["questions"]}
EMOJI = "🍞"
COLOUR = discord.Color.from_rgb(196, 140, 72)  # Golden crust
LETTERS = ["🇦", "🇧", "🇨", "🇩"]
WEEK = timedelta(days=7)
STREAK_SHOWN = 3  # A run of right answers this long is mentioned with the answer
SHOWN = 15  # On /bread scores
NOTE_LENGTH = 300  # The book's own words, with the answer
BREADS_SHOWN = 12  # On the rap sheet, one 🍞 each up to this many, then a count
# Your loaf, by right answers: the most you've reached (from 0, 5, 15...).
LOAVES = [(0, "Crumb"), (5, "Crust"), (15, "Bap"), (30, "Bloomer"), (60, "Cottage loaf"), (100, "Master baker")]
NOBODY_ANSWERED = [
    "Nobody had a go. The dough sits there, unproved.",
    "Not a single answer. Stale, the lot of you.",
    "Nobody turned up. The loaf went in and came out again, unwitnessed.",
]
NOBODY_RIGHT = [
    "Nobody got it. Half-baked, every one of you.",
    "All wrong. Not one of you rose to the occasion.",
    "Nobody. Back in the oven, the lot of you.",
]


def now() -> datetime:
    return datetime.now(timezone.utc)


def breads(right: int, unabridged: bool = False) -> str:
    """Someone's 🍞, one for each question they've got right, for their rap sheet: 🍞🍞🍞, or a count past a
    dozen; `unabridged`, every last one of them (!breadsheet)."""
    if not right:
        return "No 🍞 yet"
    return "🍞" * right if unabridged or right <= BREADS_SHOWN else f"🍞 ×{right:,}"


def loaf(right: int) -> str:
    """Someone's loaf, by how many they've got right."""
    return [name for least, name in LOAVES if right >= least][-1]


# --- Bakes: a day's question, open on a server until the next day's post ---
@dataclass
class Bake:
    id: int
    guild_id: int
    channel_id: int
    message_id: int | None
    question_id: str
    options: list[str]
    correct: int
    opened_at: str
    closed_at: str | None

    @property
    def question(self) -> dict | None:
        """Its question, or None if it's since been taken out of the bank."""
        return QUESTIONS.get(self.question_id)

    @property
    def asked(self) -> str:
        return self.question["question"] if self.question else "A question since taken off the menu"

    @property
    def number(self) -> int:
        """Which of the server's questions this is: "No. 12"."""
        return db.conn.execute("SELECT COUNT(*) FROM bread_bakes WHERE guild_id = ? AND id <= ?",
                               (self.guild_id, self.id)).fetchone()[0]


COLUMNS = "id, guild_id, channel_id, message_id, question_id, options, correct, opened_at, closed_at"


def _bake(row) -> Bake | None:
    if not row:
        return None
    values = list(row)
    values[5] = json.loads(values[5])
    return Bake(*values)


def get_bake(bake_id: int) -> Bake | None:
    return _bake(db.conn.execute(f"SELECT {COLUMNS} FROM bread_bakes WHERE id = ?", (bake_id,)).fetchone())


def current(guild_id: int) -> Bake | None:
    """The server's open question: today's."""
    return _bake(db.conn.execute(f"SELECT {COLUMNS} FROM bread_bakes WHERE guild_id = ? AND closed_at IS NULL "
                                 "ORDER BY id DESC", (guild_id,)).fetchone())


def last_closed(guild_id: int) -> Bake | None:
    return _bake(db.conn.execute(f"SELECT {COLUMNS} FROM bread_bakes WHERE guild_id = ? AND closed_at IS NOT NULL "
                                 "ORDER BY id DESC", (guild_id,)).fetchone())


def pick_question(guild_id: int) -> dict:
    """One the server hasn't had (or, once it's had them all, any): a kind first, then one of that kind's."""
    asked = {row[0] for row in db.conn.execute("SELECT question_id FROM bread_bakes WHERE guild_id = ?",
                                               (guild_id,))}
    fresh = [q for q in QUESTIONS.values() if q["id"] not in asked] or list(QUESTIONS.values())
    kind = random.choice(sorted({q["kind"] for q in fresh}))
    return random.choice([q for q in fresh if q["kind"] == kind])


def open_bake(guild_id: int, channel_id: int) -> Bake:
    """Today's question, with its answers in a fresh order."""
    question = pick_question(guild_id)
    options = [question["answer"], *question["wrong"]]
    random.shuffle(options)
    cursor = db.conn.execute(
        "INSERT INTO bread_bakes (guild_id, channel_id, question_id, options, correct, opened_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (guild_id, channel_id, question["id"], json.dumps(options), options.index(question["answer"]),
         now().isoformat()))
    db.conn.commit()
    return get_bake(cursor.lastrowid)


def close_bake(bake: Bake) -> None:
    db.conn.execute("UPDATE bread_bakes SET closed_at = ? WHERE id = ?", (now().isoformat(), bake.id))
    db.conn.commit()


def record_answer(bake_id: int, user_id: int, choice: int) -> tuple[str, Bake | None, int | None]:
    """("locked", the bake, None) for a new answer; ("already", it, their answer) if they've answered; ("closed", it
    or None, None) once its answer's out."""
    bake = get_bake(bake_id)
    if bake is None or bake.closed_at:
        return "closed", bake, None
    row = db.conn.execute("SELECT choice FROM bread_answers WHERE bake_id = ? AND user_id = ?",
                          (bake_id, user_id)).fetchone()
    if row:
        return "already", bake, row[0]
    db.conn.execute("INSERT INTO bread_answers (bake_id, guild_id, user_id, choice, correct, answered_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)", (bake_id, bake.guild_id, user_id, choice, int(choice == bake.correct),
                                                  now().isoformat()))
    db.conn.commit()
    return "locked", bake, None


def answers(bake: Bake) -> list[tuple[int, int, bool]]:
    """(user, choice, right) for everyone who answered, in the order they did."""
    return [(user, choice, bool(right)) for user, choice, right in db.conn.execute(
        "SELECT user_id, choice, correct FROM bread_answers WHERE bake_id = ? ORDER BY answered_at, rowid",
        (bake.id,))]


# --- Scores ---
def streak(guild_id: int, user_id: int) -> int:
    """How many of the server's questions, up to the last one answered, they've got right in a row."""
    rows = db.conn.execute(
        "SELECT a.correct FROM bread_bakes b LEFT JOIN bread_answers a ON a.bake_id = b.id AND a.user_id = ? "
        "WHERE b.guild_id = ? AND b.closed_at IS NOT NULL ORDER BY b.id DESC", (user_id, guild_id))
    count = 0
    for (right,) in rows:
        if not right:
            break
        count += 1
    return count


def scores(guild_id: int, since: datetime | None = None) -> list[tuple[int, int, int]]:
    """(user, right, answered) on questions whose answer is out (since a time, if given), best first: most right,
    then fewest tries."""
    where, params = db.scope(guild_id)
    sql = (f"SELECT a.user_id, SUM(a.correct), COUNT(*) FROM (SELECT * FROM bread_answers WHERE {where}) a "
           "JOIN bread_bakes b ON b.id = a.bake_id WHERE b.closed_at IS NOT NULL")
    if since:
        sql, params = sql + " AND b.closed_at >= ?", [*params, since.isoformat()]
    sql += " GROUP BY a.user_id ORDER BY SUM(a.correct) DESC, COUNT(*) ASC, a.user_id"
    return [tuple(row) for row in db.conn.execute(sql, params)]


def record(guild_id: int, user_id: int) -> tuple[int, int]:
    """(right, answered) for one person, for their rap sheet."""
    found = next((row for row in scores(guild_id) if row[0] == user_id), None)
    return (found[1], found[2]) if found else (0, 0)


# --- What's posted ---
def question_embed(bake: Bake, answer_at: datetime | None) -> discord.Embed:
    lines = [f"**{bake.asked}**", ""] + [f"{LETTERS[n]} {oldbooks.escape(option)}"
                                         for n, option in enumerate(bake.options)]
    when = f" The answer comes out <t:{int(answer_at.timestamp())}:R>." if answer_at else ""
    lines += ["", f"-# Answer with the buttons: only you see your answer, and there's no re-kneading it.{when}"]
    embed = discord.Embed(title=f"{EMOJI} How well do you bread? No. {bake.number}", description="\n".join(lines),
                          color=COLOUR)
    if bake.question:
        embed.set_footer(text=f"From {bake.question['source']}")
    return embed


def answer_embed(bake: Bake) -> discord.Embed:
    """Yesterday's bake: the answer, who got it right, the book's own words and the week's top bakers."""
    question = bake.question
    lines = [f"**{bake.asked}**", f"It was {LETTERS[bake.correct]} **{oldbooks.escape(bake.options[bake.correct])}**."]
    if question and question.get("note"):
        lines.append(f"> {oldbooks.escape(oldbooks.clip(' '.join(question['note'].split()), NOTE_LENGTH))}")
    if question:
        lines.append(f"-# From [{oldbooks.escape(question['source'])}]({question['link']})")
    given = answers(bake)
    lines.append("")
    right = [user for user, _, ok in given if ok]
    if not given:
        lines.append(random.choice(NOBODY_ANSWERED))
    elif not right:
        lines.append(random.choice(NOBODY_RIGHT))
    else:
        named = []
        for user in right:
            run = streak(bake.guild_id, user)
            named.append(f"<@{user}>" + (f" ({run} in a row)" if run >= STREAK_SHOWN else ""))
        lines.append("🍞 for " + ", ".join(named))
    if given:
        lines.append(" · ".join(f"{LETTERS[n]} {sum(1 for _, choice, _ in given if choice == n)}" for n in range(4)))
    week = [(user, right) for user, right, _ in scores(bake.guild_id, since=now() - WEEK) if right][:5]
    if week:
        lines.append("🏆 This week's top bakers: " + " · ".join(f"<@{user}> {right}" for user, right in week))
    return discord.Embed(title=f"{EMOJI} Yesterday's bake: No. {bake.number}", description="\n".join(lines)[:4096],
                         color=COLOUR)


class Answer(discord.ui.DynamicItem[discord.ui.Button], template=r"bread:(?P<bake>[0-9]+):(?P<choice>[0-3])"):
    """One of a question's four buttons. Its custom_id says which question and which answer, so it works after a
    restart."""

    def __init__(self, bake_id: int, choice: int):
        super().__init__(discord.ui.Button(emoji=LETTERS[choice], style=discord.ButtonStyle.secondary,
                                           custom_id=f"bread:{bake_id}:{choice}"))
        self.bake_id, self.choice = bake_id, choice

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match):
        return cls(int(match["bake"]), int(match["choice"]))

    async def callback(self, interaction: discord.Interaction):
        await give_answer(interaction, self.bake_id, self.choice)


def answer_view(bake: Bake) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for choice in range(4):
        view.add_item(Answer(bake.id, choice))
    return view


def answer_time(guild_id: int) -> datetime | None:
    """When the server's next post (and so today's answer) is due, if it's set up."""
    setup = daily.get_setup(guild_id, DAILY.kind)
    return daily.next_post(setup.clock, now()) if setup else None


async def give_answer(interaction: discord.Interaction, bake_id: int, choice: int) -> None:
    """A button pressed: the answer locked in, privately. Nobody's told what anyone picked until the next day."""
    status, bake, previous = record_answer(bake_id, interaction.user.id, choice)
    if status == "closed":
        text = (f"{EMOJI} That one's out of the oven: its answer's out. Today's question is in the latest post (or "
                "`/bread`).")
    elif status == "already":
        text = (f"{EMOJI} You've already answered: {LETTERS[previous]} *{oldbooks.escape(bake.options[previous])}*. "
                "No re-kneading.")
    else:
        log.info("[%s] %s answered /bread %d", getattr(interaction.guild, "name", bake.guild_id), interaction.user,
                 bake.id)  # Not what they said
        at = answer_time(bake.guild_id)
        when = f" <t:{int(at.timestamp())}:R>" if at else " with the next question"
        text = (f"🔒 Locked in: {LETTERS[choice]} *{oldbooks.escape(bake.options[choice])}*. "
                f"Were you cooking? Find out{when}.")
    await interaction.response.send_message(text, ephemeral=True)


async def post_bread(channel: discord.abc.Messageable, last: str | None) -> None:
    """The daily bread: yesterday's answer (if there was a question), then today's question."""
    guild_id = channel.guild.id
    embeds = []
    if previous := current(guild_id):
        close_bake(previous)
        embeds.append(answer_embed(get_bake(previous.id)))
    bake = open_bake(guild_id, channel.id)
    embeds.append(question_embed(bake, answer_time(guild_id)))
    message = await channel.send(embeds=embeds, view=answer_view(bake), allowed_mentions=NO_PINGS)
    if message is not None:
        db.conn.execute("UPDATE bread_bakes SET message_id = ? WHERE id = ?", (message.id, bake.id))
        db.conn.commit()
    return None


DAILY = daily.register(daily.Daily(
    "bread", "The daily bread", EMOJI, "bread", post=post_bread,
    note=lambda: "One question a day. Answers are private and final; each comes out with the next question."))


# --- The commands ---
@commands.hybrid_group(name="bread", fallback="today", invoke_without_command=True,
                       description="How well do you 🍞? A question a day from the old books: answer it privately.")
@commands.guild_only()
async def bread(ctx: commands.Context):
    """How well do you 🍞? Or, as they'd put it in Somerset, how well do you be read? One question a day from the old
    books: what a lost word or a bit of 1811 slang meant, how Bierce defined something, what a flower said, or what
    you'd have done at a Victorian dinner or on Plough Monday in 1826. Four answers, one right. Press a button to
    answer, whenever you like: only you see your answer, and you can't change it. The next day's post (the daily bread)
    gives the answer, who got it right, the book's own words and a link, with the new question. This shows you today's
    question (privately), and yesterday's answer.

    Someone with Manage Server sets it up with `/bread setup here [time]` in the channel it should post in (9am
    unless told otherwise, where the bot is); the first question goes up straight away. `/bread scores` is the
    table, with everyone's loaf, from Crumb to Master baker. Each day's winners get a 🍞 on their rap sheet."""
    bake = current(ctx.guild.id)
    if bake is None:
        setup = daily.get_setup(ctx.guild.id, DAILY.kind)
        later = (f"The first question comes out <t:{int(setup.next_run_at.timestamp())}:R>." if setup else
                 "Someone with Manage Server can run `/bread setup here` in the channel it should use.")
        await ctx.send(f"{EMOJI} Nothing's in the oven here yet. {later}", ephemeral=True)
        return
    embeds = [question_embed(bake, answer_time(ctx.guild.id))]
    if previous := last_closed(ctx.guild.id):
        embeds.append(answer_embed(previous))
    await ctx.send(embeds=embeds, view=answer_view(bake), ephemeral=True, allowed_mentions=NO_PINGS)


@bread.command(name="scores", aliases=["leaderboard", "loaves"],
                   description="Who's the top baker: everyone's right answers, and their loaf.")
@commands.guild_only()
async def bread_scores(ctx: commands.Context):
    """Everyone's right answers, best first (fewest tries breaks a tie), with their loaf (Crumb, Crust, Bap,
    Bloomer, Cottage loaf, and at 100 right, Master baker) and anyone on a run of right answers. An answer counts once
    it's out."""
    rows = scores(ctx.guild.id)
    if not rows:
        await ctx.send(f"{EMOJI} No scores yet. Nobody's had a go.", ephemeral=True)
        return
    lines = []
    for rank, (user, right, answered) in enumerate(rows[:SHOWN], 1):
        run = streak(ctx.guild.id, user)
        lines.append(f"{rank}. <@{user}>: **{right}** right of {answered}, {loaf(right).lower()}"
                     + (f", {run} in a row" if run >= 2 else ""))
    embed = discord.Embed(title=f"{EMOJI} How well do you bread?", description="\n".join(lines), color=COLOUR)
    embed.set_footer(text="Crumb · Crust (5) · Bap (15) · Bloomer (30) · Cottage loaf (60) · Master baker (100). "
                          "Every right answer is a 🍞 on the rap sheet.")
    await ctx.send(embed=embed, allowed_mentions=NO_PINGS)


@bread.group(name="setup", invoke_without_command=True,
                 description="The daily bread: where and when the question is posted.")
@commands.guild_only()
async def bread_setup(ctx: commands.Context):
    await daily.show(ctx, DAILY)


@bread_setup.command(name="here", description="Post the daily bread (yesterday's answer, today's question) here.")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
@app_commands.describe(time="When each day: yesterday's answer and today's question (9am, 0730, 18:30). Empty: 9am")
async def bread_setup_here(ctx: commands.Context, *, time: str | None = None):
    await daily.setup_here(ctx, DAILY, time)
    if daily.get_setup(ctx.guild.id, DAILY.kind) and current(ctx.guild.id) is None:  # The first one, straight away
        await post_bread(ctx.channel, None)


@bread_setup.command(name="stop", description="Stop posting the daily bread.")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def bread_setup_stop(ctx: commands.Context):
    await daily.stop(ctx, DAILY)


@bread_setup.command(name="show", description="Where and when the daily bread is posted.")
@commands.guild_only()
async def bread_setup_show(ctx: commands.Context):
    await daily.show(ctx, DAILY)


async def setup(bot: commands.Bot):
    bot.add_command(bread)
    bot.add_dynamic_items(Answer)  # Every question's buttons, posted before a restart too
    daily.start()
