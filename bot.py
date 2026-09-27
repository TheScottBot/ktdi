import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

SPRAY_GIF_URL = "https://klipy.com/gifs/spray-bottle-3"
SPRAY_EMOJI = "💦"
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")


class KTDIBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        # Needed to read "<prefix>spray" from messages. Must also be enabled in the Developer Portal.
        intents.message_content = True
        super().__init__(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)

    async def setup_hook(self):
        await self.tree.sync()


bot = KTDIBot()


@bot.hybrid_command(name="spray", description="Spray the degenerate.")
async def spray(ctx: commands.Context):
    await ctx.send(SPRAY_GIF_URL)


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    # Reacting 💦 to a message sprays whoever sent it.
    if str(payload.emoji) != SPRAY_EMOJI or payload.user_id == bot.user.id:
        return
    channel = bot.get_channel(payload.channel_id)
    if channel is None:
        return
    target = f"<@{payload.message_author_id}> " if payload.message_author_id else ""
    await channel.send(f"{target}{SPRAY_GIF_URL}")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id}), prefix: {COMMAND_PREFIX!r}")


def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit("DISCORD_TOKEN is not set. Copy .env.example to .env and add your token.")
    bot.run(token)


if __name__ == "__main__":
    main()
