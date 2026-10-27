"""/play: start a game in the channel. One command for every game (ktdi/sessions.py has the engine; each game is its
own feature, registered with sessions.register), so new games don't add to Discord's command list.

/play game:<game> [pace] [start] posts a lobby: people join with a button, and the host starts it (or, async, it
starts itself at `start` with whoever's in). Everything after that happens on the game's board, by buttons.
"""

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import daily, sessions
from ktdi.common import NO_PINGS, log
from ktdi.lib import reminders

HELP_CATEGORY = "🎲 Fun"


NOW = {"now", "right now", "asap", "straight away"}  # start:now, either pace: no wait, the host starts it


def play_command(games: dict[str, sessions.Game]) -> commands.HybridCommand:
    """/play, with every registered game in its menu."""

    async def play(ctx: commands.Context, game: str, pace: str = "live", *, start: str | None = None):
        chosen = games.get(game.lower().strip())
        if chosen is None:
            await ctx.send(f"There's no game called `{game}`. Try: {', '.join(f'`{key}`' for key in games)}.",
                           ephemeral=True)
            return
        pace = pace.lower().strip()
        if pace not in sessions.PACES or pace not in chosen.paces:
            await ctx.send(f"{chosen.title} can be played: {', '.join(chosen.paces)}.", ephemeral=True)
            return
        if going := sessions.active_in(ctx.channel.id):
            await ctx.send(f"There's already a game of {going.game.title} here: one at a time.", ephemeral=True)
            return
        starts_at = None
        if start and " ".join(start.lower().split()) in NOW:
            start = None  # Now: the lobby's open, and the host starts it as soon as enough are in
        if start:
            if pace != "async":
                await ctx.send("A start time is for games played through the day (`pace:async`): live ones start "
                               "when the host presses Start.", ephemeral=True)
                return
            try:
                hour, minute = reminders.parse_clock(start)
            except reminders.ScheduleError as error:
                await ctx.send(str(error), ephemeral=True)
                return
            starts_at = daily.next_post(f"{hour:02d}:{minute:02d}", sessions.now())
        session = sessions.create(ctx.guild.id, ctx.channel.id, chosen, ctx.author.id, pace, [ctx.author.id],
                                  starts_at)
        message = await ctx.send(embed=sessions.lobby_embed(session), view=sessions.view_for(session),
                                 allowed_mentions=NO_PINGS)
        session.message_id = message.id
        sessions.save(session)
        log.info("[%s] %s opened a lobby for %s (%s)", ctx.guild.name, ctx.author, chosen.key, pace)

    lines = "\n".join(f"• **{g.emoji} {g.title}** (`{key}`, {g.min_players}–{g.max_players} players): {g.blurb}"
                      for key, g in games.items())
    play.__doc__ = (
        "Starts a game in this channel: a lobby people join with a button, then the host presses Start. Everything "
        "else happens by buttons on the game's board: 🃏 **My card** shows you yours (only you see it), a "
        "button for your move when it's your turn (it says what: in Crust, ✍️ **Give your clue**, then 🗳️ **Vote**, "
        "a list of names to pick from), 🔁 **Play again** at the end. Missed the start? "
        "➕ **Join next round** on the board, and you're dealt in when someone presses Play again. The board moves "
        "back to the bottom of the channel when chat's buried it.\n\n"
        "**Two paces:** ⚡ `live`, for playing together now (moves in seconds), or 🕰️ `async`, through the day: "
        "each move has 4 hours, and the clock stops overnight (23:00–07:00 UK), so nobody's timed out while asleep "
        "(moves are still taken then). An async game can start itself: `start:9am`. `start:now` (or no "
        "start) means the host starts it once enough are in.\n\n"
        "**Pings:** nobody's pinged unless they've pressed 🔔 **Ping me**, so a muted channel stays muted. One game "
        "per channel at a time; the host (or someone with Manage Server) can cancel it.\n\n**The games:**\n" + lines)
    play = app_commands.describe(game="Which game", pace="live: together, now. async: through the day (4-hour moves)",
                                 start="now (the host starts it), or async only: a time it starts itself, with whoever's in (9am)")(play)
    play = app_commands.choices(
        game=[app_commands.Choice(name=f"{g.emoji} {g.title}", value=key) for key, g in games.items()][:25],
        pace=[app_commands.Choice(name="⚡ Live: together, now", value="live"),
              app_commands.Choice(name="🕰️ Through the day: 4-hour moves", value="async")])(play)
    command = commands.hybrid_command(name="play", description="Start a game here: people join, then play it live "
                                                               "or through the day.")(play)
    return commands.guild_only()(command)


async def setup(bot: commands.Bot):
    bot.add_command(play_command(sessions.GAMES))
    bot.add_dynamic_items(sessions.GameButton)  # Every game's buttons, from before a restart too
    bot.add_listener(sessions.chatted, "on_message")  # Moves a game's board back down when chat's buried it
    sessions.start_loop()
