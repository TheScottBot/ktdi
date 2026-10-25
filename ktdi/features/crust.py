"""Crust (/play game:crust): one of you is a Changeling, a fairy swapped in for one of the Household, who doesn't
know the old word everyone else does.

Everyone's card has the same theme and shortlist of eight old words, with their meanings (from the old books: lost
words, Grose's slang, the language of flowers...). The Household's cards mark which is the word; the Changeling's
doesn't. In a random order, everyone gives a clue (a word, or a few: short is better): enough to show they know it, not so much that the
Changeling can work it out. Then everyone votes, privately, for who they think the Changeling is. If they're caught
(most votes, no tie), they get one guess at the word.

Scoring, as the game it's based on: the Changeling not caught +2; caught, but guessing the word, +1; caught and
wrong, the Household +1 each. The rules are here; everything else (the lobby, cards, deadlines, live or async) is
the engine's (ktdi/sessions.py). The cards are in ktdi/lib/crust.json, built by ktdi/tools/crust_build.py from
words that already passed /bread's review, sorted into themes and checked so each card's eight could all fit it.
"""

import json
import random
import re
from collections import Counter
from pathlib import Path

import discord
from discord.ext import commands

from ktdi import db, oldbooks, sessions

HELP_CATEGORY = "🎲 Fun"
DATA = Path(__file__).resolve().parent.parent / "lib" / "crust.json"
CARDS: list[dict] = json.loads(DATA.read_text(encoding="utf-8"))["cards"] if DATA.exists() else []
RECENT = 30  # A server doesn't get a card it's had in its last this-many games
WORD_RE = re.compile(r"[^\W\d_]+(?:['-][^\W\d_]+)*")  # A word: letters, with apostrophes and hyphens inside
CLUE_LENGTH = 60  # A word or a few, not a sentence
SMALL_WORDS = {"a", "an", "and", "at", "by", "for", "in", "of", "on", "or", "the", "to", "up", "with"}  # Never banned
HOURS = 3600


class Crust(sessions.Game):
    key = "crust"
    title = "Crust"
    emoji = "🧚"
    blurb = "One of you is a Changeling who doesn't know the old word. Give short clues, then find them."
    rules = ("**How it goes:** everyone sees the same eight old words. The Household know which one it is; the "
             "Changeling doesn't. Each gives a short clue in turn (a word or a few), then everyone votes for the Changeling. Caught, "
             "they get one guess at the word.\n**Points:** Changeling escapes +2 · caught but guesses it +1 · caught "
             "and wrong, the Household +1 each.")
    min_players, max_players = 3, 10
    timings = {"live": {"clue": 45, "vote": 60, "guess": 45},
               "async": {"clue": 4 * HOURS, "vote": 4 * HOURS, "guess": 4 * HOURS}}

    # --- Dealing ---
    def deal(self, session: sessions.Session) -> None:
        card = pick_card(session.guild_id)
        players = list(session.players)
        order = random.sample(players, len(players))
        session.state = {"card": card["id"], "target": random.randrange(len(card["words"])),
                         "changeling": random.choice(players), "order": order, "turn": 0, "stage": "clue",
                         "clues": {}, "votes": {}, "suspect": None, "guess": None, "outcome": None}

    # --- What everyone sees ---
    def card(self, session: sessions.Session, user_id: int) -> discord.Embed:
        state, card = session.state, card_of(session)
        changeling = user_id == state["changeling"]
        lines = []
        for n, entry in enumerate(card["words"]):
            line = f"**{oldbooks.escape(entry['word'])}**: {oldbooks.escape(entry['meaning'])}"
            lines.append(f"➡️ {line}" if not changeling and n == state["target"] else f"▫️ {line}")
        if changeling:
            intro = ("You're the **Changeling** 🧚. The Household all know which of these old words it is; you don't. "
                     "Give a clue that could fit, listen to theirs, and don't get caught.")
        else:
            intro = ("You're one of the **Household** 🏠. The word is the one marked ➡️. Give a clue that shows you "
                     "know it without giving it away: one of you is a Changeling who doesn't.")
        embed = discord.Embed(title=f"{self.emoji} {card['theme']}", description=intro + "\n\n" + "\n".join(lines),
                              color=sessions.COLOUR)
        embed.set_footer(text="Only you can see this. Your clue: short (a word or a few), and none of these eight.")
        return embed

    def step(self, session: sessions.Session) -> tuple[str, str]:
        state = session.state
        if state["stage"] == "clue":
            return f"clue:{state['order'][state['turn']]}", "clue"
        return state["stage"], "vote" if state["stage"] == "vote" else "guess"

    def waiting_on(self, session: sessions.Session) -> list[int]:
        state = session.state
        if state["stage"] == "clue":
            return [state["order"][state["turn"]]]
        if state["stage"] == "vote":
            return [user for user in session.players if str(user) not in state["votes"]]
        if state["stage"] == "guess":
            return [state["changeling"]]
        return []

    def status(self, session: sessions.Session) -> str:
        state = session.state
        theme = card_of(session)["theme"]
        given = clue_lines(session)
        so_far = f"\n**Clues:** {given}" if given else ""
        if state["stage"] == "clue":
            return f"**{theme}.** Clues, one each: {len(state['clues'])} of {len(state['order'])}.{so_far}"
        if state["stage"] == "vote":
            return (f"**{theme}.** The clues are in: vote for the Changeling ({len(state['votes'])} of "
                    f"{len(session.players)} voted).{so_far}")
        if state["stage"] == "guess":
            return (f"**{theme}.** The Household have caught <@{state['changeling']}>, the Changeling! One guess at the "
                    f"word, and they still score.{so_far}")
        return f"**{theme}.** Over: see the reveal.{so_far}"

    # --- Moves ---
    def move_button(self, session: sessions.Session) -> tuple[str, str]:
        return {"clue": ("Give your clue", "✍️"), "vote": ("Vote", "🗳️"),
                "guess": ("Guess the word", "🎯")}.get(session.state["stage"], ("Your move", "✍️"))

    def ask(self, session: sessions.Session, user_id: int) -> sessions.Ask | str:
        state = session.state
        if state["stage"] == "clue":
            turn = state["order"][state["turn"]]
            if user_id != turn:
                return f"Not your turn: it's <@{turn}>'s."
            return sessions.Ask("Your clue: short is best", max_length=CLUE_LENGTH,
                                placeholder="A word or a few, not one of the eight")
        if state["stage"] == "vote":
            if str(user_id) in state["votes"]:
                return "You've voted. Wait for the rest."
            return sessions.Ask("Who's the Changeling? Pick a name", kind="choice", choices=[
                (sessions.name_of(session, user), str(user)) for user in session.players if user != user_id])
        if state["stage"] == "guess":
            if user_id != state["changeling"]:
                return "The Changeling's guessing. Keep a straight face."
            return sessions.Ask("Which word is it? Pick one", kind="choice",
                                choices=[(entry["word"], str(n)) for n, entry in enumerate(card_of(session)["words"])])
        return "It's over."

    def answer(self, session: sessions.Session, user_id: int, value: str) -> sessions.Result:
        state = session.state
        if state["stage"] == "clue":
            word = " ".join(value.split())
            if not WORD_RE.search(word):
                return sessions.Result("A clue needs a word in it.", ok=False)
            if banned(card_of(session), word):
                return sessions.Result("Not one of the eight (or part of one): that'd give it away.", ok=False)
            state["clues"][str(user_id)] = word
            state["turn"] += 1
            posts = [f"🗣️ <@{user_id}>: **{oldbooks.escape(word)}**"]
            if state["turn"] >= len(state["order"]):
                state["stage"] = "vote"
                posts.append("🗳️ **All the clues are in.** Who's the Changeling? Press 🗳️ **Vote** on the board and pick a name.")
            return sessions.Result(f"Your clue: **{oldbooks.escape(word)}**.", posts)
        if state["stage"] == "vote":
            if value == str(user_id) or int(value) not in session.players:
                return sessions.Result("Not yourself, and only someone playing.", ok=False)
            state["votes"][str(user_id)] = int(value)
            posts = []
            if len(state["votes"]) >= len(session.players):
                posts = resolve_votes(session)
            return sessions.Result(f"You voted for {sessions.name_of(session, int(value))}.", posts)
        if state["stage"] == "guess":
            state["guess"] = int(value)
            return sessions.Result("Your guess is in.", conclude(session))
        return sessions.Result("It's over.", ok=False)

    def timeout(self, session: sessions.Session) -> list[str]:
        state = session.state
        if state["stage"] == "clue":
            silent = state["order"][state["turn"]]
            state["clues"][str(silent)] = None
            state["turn"] += 1
            posts = [f"🤐 <@{silent}> said nothing: time's up. Suspicious."]
            if state["turn"] >= len(state["order"]):
                state["stage"] = "vote"
                posts.append("🗳️ **All the clues are in.** Who's the Changeling? Press 🗳️ **Vote** on the board and pick a name.")
            return posts
        if state["stage"] == "vote":
            return resolve_votes(session)  # With the votes that are in
        if state["stage"] == "guess":
            state["guess"] = None  # Out of time: no guess, so wrong
            return conclude(session)
        return []

    def finished(self, session: sessions.Session) -> bool:
        return session.state.get("stage") == "done"

    # --- The end ---
    def reveal(self, session: sessions.Session) -> discord.Embed:
        state, card = session.state, card_of(session)
        entry = card["words"][state["target"]]
        changeling, outcome = state["changeling"], state["outcome"]
        title = {"escaped": "🧚 The Changeling got away with it!",
                 "guessed": "🧚 Caught, but the Changeling knew the word!",
                 "caught": "🏠 The Household found the Changeling!"}[outcome]
        lines = [f"The Changeling was <@{changeling}>.",
                 f"The word was **{oldbooks.escape(entry['word'])}**: *{oldbooks.escape(entry['meaning'])}*.",
                 f"-# From [{oldbooks.escape(entry['source'])}]({entry['link']})", ""]
        clues = clue_lines(session)
        if clues:
            lines.append(f"**Clues:** {clues}")
        if state["votes"]:
            lines.append("**Votes:** " + " · ".join(f"<@{voter}> → <@{suspect}>"
                                                    for voter, suspect in state["votes"].items()))
        if outcome != "escaped" and state["guess"] is not None:
            guessed = card["words"][state["guess"]]["word"]
            lines.append(f"**The Changeling guessed:** {oldbooks.escape(guessed)}")
        points = [f"+{p} <@{user}>" for user, (p, _, _) in self.results(session).items() if p]
        lines += ["", "**Points:** " + (" · ".join(points) or "none")]
        embed = discord.Embed(title=title, description="\n".join(lines)[:4096], color=sessions.COLOUR)
        embed.set_footer(text=f"{card['theme']} · 🔁 Play again for another round, same players.")
        return embed

    def results(self, session: sessions.Session) -> dict[int, tuple[int, bool, str]]:
        state = session.state
        changeling, outcome = state["changeling"], state["outcome"]
        out = {}
        for user in session.players:
            if user == changeling:
                points = {"escaped": 2, "guessed": 1, "caught": 0}[outcome]
                out[user] = (points, outcome != "caught", "changeling")
            else:
                out[user] = (1 if outcome == "caught" else 0, outcome == "caught", "household")
        return out


# --- The rules' workings ---
def card_of(session: sessions.Session) -> dict:
    return next(card for card in CARDS if card["id"] == session.state["card"])


def pick_card(guild_id: int) -> dict:
    """A card this server hasn't had lately."""
    recent = set()
    for (state,) in db.conn.execute("SELECT state FROM game_sessions WHERE guild_id = ? AND game = 'crust' "
                                    "ORDER BY id DESC LIMIT ?", (guild_id, RECENT)):
        recent.add(json.loads(state).get("card"))
    return random.choice([card for card in CARDS if card["id"] not in recent] or CARDS)


def banned(card: dict, clue: str) -> bool:
    """Whether a clue has one of the eight words in it, or part of one (any of them, so nobody learns which is the
    word by being turned down). Small words ("to", "of") don't count: "To Sham Abram" doesn't ban every "to"."""
    said = set(WORD_RE.findall(clue.casefold().replace("’", "'")))
    for entry in card["words"]:
        words = set(WORD_RE.findall(entry["word"].casefold().replace("’", "'")))
        if said & (words - SMALL_WORDS):
            return True
    return False


def clue_lines(session: sessions.Session) -> str:
    state = session.state
    shown = []
    for user in state["order"]:
        if str(user) in state["clues"]:
            word = state["clues"][str(user)]
            shown.append(f"<@{user}> *{oldbooks.escape(word)}*" if word else f"<@{user}> 🤐")
    return " · ".join(shown)


def resolve_votes(session: sessions.Session) -> list[str]:
    """The votes are in (or time's up): the Changeling's caught if they alone have the most."""
    state = session.state
    counts = Counter(state["votes"].values())
    top = counts.most_common(1)[0][1] if counts else 0
    leaders = [user for user, count in counts.items() if count == top]
    if len(leaders) != 1:
        state["outcome"], state["stage"] = "escaped", "done"
        return ["🗳️ **A tie.** Nobody's accused, and the Changeling slips away."]
    state["suspect"] = leaders[0]
    if leaders[0] != state["changeling"]:
        state["outcome"], state["stage"] = "escaped", "done"
        return [f"🗳️ The Household accuse <@{leaders[0]}>... who's one of them. The real Changeling slips away."]
    state["stage"] = "guess"
    return [f"🗳️ The Household accuse <@{leaders[0]}>, and they're right: the Changeling! One guess at the word, "
            f"and they still score."]


def conclude(session: sessions.Session) -> list[str]:
    state = session.state
    state["outcome"] = "guessed" if state["guess"] == state["target"] else "caught"
    state["stage"] = "done"
    return []


GAME = sessions.register(Crust())


async def setup(bot: commands.Bot):
    pass  # A game, not a command: /play has it (ktdi/features/play.py)
