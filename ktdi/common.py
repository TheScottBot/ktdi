"""Small helpers shared by several features."""

import logging
from dataclasses import dataclass

import discord
from discord.ext import commands

log = logging.getLogger("ktdi")

# The running bot, for code with no ctx to hand (background loops, reaction listeners). Set by create_bot().
bot: commands.Bot | None = None

NO_PINGS = discord.AllowedMentions.none()


@dataclass
class Reply:
    content: str | None = None
    embed: discord.Embed | None = None
    private: bool = False  # Only shown to the person who asked (slash commands only).


async def send_reply(ctx: commands.Context, reply: Reply) -> None:
    await ctx.send(reply.content, embed=reply.embed, allowed_mentions=NO_PINGS)


async def respond(interaction: discord.Interaction, reply: Reply) -> None:
    await interaction.response.send_message(reply.content, embed=reply.embed, ephemeral=reply.private,
                                            allowed_mentions=NO_PINGS)


def plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


class SearchPages(discord.ui.View):
    """Search results with ◀ / ▶ buttons to page through them (/books, /rpg). Only the searcher can turn pages."""

    def __init__(self, results: list, *, title: str, line, footer: str, command: str, author_id: int,
                 per_page: int = 15, color: discord.Color = discord.Color.blurple()):
        super().__init__(timeout=600)
        self.results, self.title, self.line, self.footer = results, title, line, footer
        self.command, self.author_id, self.per_page, self.color = command, author_id, per_page, color
        self.page = 0
        self.page_count = -(-len(results) // per_page)  # Round up.
        self.message: discord.Message | None = None
        self._update_buttons()

    def embed(self) -> discord.Embed:
        start = self.page * self.per_page
        embed = discord.Embed(title=self.title, color=self.color,
                              description="\n".join(self.line(r) for r in self.results[start:start + self.per_page]))
        footer = self.footer
        if self.page_count > 1:
            footer = f"Page {self.page + 1} of {self.page_count}. " + footer
        embed.set_footer(text=footer)
        return embed

    def _update_buttons(self) -> None:
        self.previous_page.disabled = self.page == 0
        self.next_page.disabled = self.page >= self.page_count - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Matters for !books / !rpg search, which post in the channel where anyone could click.
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(f"These are someone else's results. Run your own `{self.command}`.",
                                                    ephemeral=True)
            return False
        return True

    async def _show(self, interaction: discord.Interaction) -> None:
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(self.page - 1, 0)
        await self._show(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = min(self.page + 1, self.page_count - 1)
        await self._show(interaction)

    async def on_timeout(self) -> None:
        # Buttons stop working after 10 minutes, so grey them out.
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass  # Private messages can only be edited for 15 minutes; not worth failing over.


async def send_search_pages(ctx: commands.Context, pages: SearchPages) -> None:
    """Privately (for slash), with buttons only if there's more than one page."""
    if pages.page_count == 1:
        await ctx.send(embed=pages.embed(), ephemeral=True)
        return
    pages.message = await ctx.send(embed=pages.embed(), view=pages, ephemeral=True)


async def get_member(guild: discord.Guild, user_id: int) -> discord.Member | None:
    try:
        return guild.get_member(user_id) or await guild.fetch_member(user_id)
    except discord.HTTPException:
        return None  # Left the server, or couldn't look them up.
