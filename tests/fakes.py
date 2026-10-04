"""Stand-ins for Discord objects, so commands can be run without connecting to Discord."""

import asyncio
import types
from datetime import datetime


def run(coro):
    return asyncio.run(coro)


class User:
    def __init__(self, uid: int, name: str, *, mod: bool = False, admin: bool = False):
        self.id, self.name, self.display_name = uid, name, name
        self.mention = f"<@{uid}>"
        self.bot = False
        self.guild_permissions = types.SimpleNamespace(manage_messages=mod or admin, manage_guild=admin)
        self.dms: list = []

    def __str__(self):
        return self.name

    async def send(self, content=None, file=None, **kwargs):
        self.dms.append((content, file))


class Guild:
    def __init__(self, gid: int = 111, name: str = "Test Server"):
        self.id, self.name = gid, name
        self.roles: list = []
        self.filesize_limit = 10 * 1024 * 1024

    def get_member(self, user_id):
        return None


class Sent:
    """A message the bot sent."""

    def __init__(self, content=None, embed=None, view=None, file=None, private=False, allowed_mentions=None,
                 poll=None):
        self.content, self.embed, self.view, self.file, self.poll = content, embed, view, file, poll
        self.private, self.allowed_mentions = private, allowed_mentions
        self.id = id(self)
        self.reactions: list = []
        self.edits: list[str] = []  # each content it was edited to, in order
        self.original = content

    @property
    def text(self) -> str:
        """Content plus embed title/description/fields, for easy asserts."""
        parts = [self.content or ""]
        if self.embed:
            parts += [self.embed.title or "", self.embed.description or ""]
            parts += [f"{f.name}: {f.value}" for f in self.embed.fields]
            parts += [self.embed.footer.text or ""]
        return "\n".join(p for p in parts if p)

    async def add_reaction(self, emoji):
        self.reactions.append(emoji)

    async def end_poll(self):
        self.poll._finalized = True
        return self

    async def edit(self, **kwargs):
        if "content" in kwargs:
            self.content = kwargs["content"]
            self.edits.append(kwargs["content"])


class Channel:
    def __init__(self, cid: int = 500, guild: Guild | None = None):
        self.id, self.guild = cid, guild
        self.sent: list[Sent] = []
        self.messages: dict = {}

    def __str__(self):
        return f"channel-{self.id}"

    async def send(self, content=None, embed=None, view=None, allowed_mentions=None, **kwargs):
        message = Sent(content, embed, view, allowed_mentions=allowed_mentions)
        self.sent.append(message)
        return message

    async def fetch_message(self, message_id):
        return self.messages[message_id]


class Message:
    """A message someone else wrote (e.g. one being quoted)."""

    def __init__(self, mid: int, author: User, content: str, channel: Channel | None = None):
        self.id, self.author, self.content = mid, author, content
        self.channel = channel or Channel()


class Ctx:
    """A command context: slash=True for /commands, False for !commands."""

    def __init__(self, author: User, guild: Guild | None = None, *, slash: bool = True, bot=None,
                 channel: Channel | None = None, mentions=(), reply_to: Message | None = None, content: str = ""):
        from ktdi import common
        self.author = author
        self.guild = guild if guild is not None else Guild()
        self.channel = channel or Channel(guild=self.guild)
        self.bot = bot or common.bot
        self.interaction = types.SimpleNamespace(data={}) if slash else None
        if reply_to:
            self.channel.messages[reply_to.id] = reply_to
        reference = types.SimpleNamespace(message_id=reply_to.id, resolved=None) if reply_to else None
        self.message = types.SimpleNamespace(content=content, reference=reference, mentions=list(mentions),
                                             deleted=False)

        async def delete():
            self.message.deleted = True
        self.message.delete = delete
        self.sent: list[Sent] = []

    async def send(self, content=None, embed=None, view=None, file=None, ephemeral=False, allowed_mentions=None,
                   poll=None, **kwargs):
        message = Sent(content, embed, view, file, ephemeral, allowed_mentions, poll)
        self.sent.append(message)
        self.channel.messages[message.id] = message  # so it can be fetched again, like a real one
        return message

    async def reply(self, content=None, **kwargs):
        return await self.send(content, **kwargs)

    async def defer(self, ephemeral=False):
        pass

    @property
    def last(self) -> Sent:
        return self.sent[-1]


class Interaction:
    """For pure slash commands (quotes) and forms."""

    def __init__(self, user: User, guild: Guild | None = None, channel_id: int = 500):
        self.user = user
        self.guild = guild if guild is not None else Guild()
        self.guild_id = self.guild.id
        self.channel_id = channel_id
        self.sent: list[Sent] = []
        self.modal = None
        self.response = self

    async def send_message(self, content=None, embed=None, ephemeral=False, allowed_mentions=None, **kwargs):
        self.sent.append(Sent(content, embed, private=ephemeral, allowed_mentions=allowed_mentions))

    async def send_modal(self, modal):
        self.modal = modal

    async def edit_message(self, embed=None, view=None):
        self.sent.append(Sent(embed=embed, view=view))

    @property
    def last(self) -> Sent:
        return self.sent[-1]


class FakeBot:
    def __init__(self):
        self.user = types.SimpleNamespace(id=999)
        self.channels: dict[int, Channel] = {}
        self.guilds: list[Guild] = []
        self.commands = []
        self.activity = None

    async def change_presence(self, activity=None):
        self.activity = activity

    def get_channel(self, channel_id):
        return self.channels.get(channel_id)

    def add_channel(self, channel: Channel) -> Channel:
        self.channels[channel.id] = channel
        return channel

    async def wait_until_ready(self):
        pass


class FrozenClock:
    """Makes datetime.now() return a chosen time in the given modules."""

    def __init__(self, monkeypatch):
        self.monkeypatch = monkeypatch
        self.now = None

    def set(self, moment: datetime, *modules):
        self.now = moment
        clock = self

        class Frozen(datetime):
            @classmethod
            def now(cls, tz=None):
                return clock.now

        for module in modules:
            self.monkeypatch.setattr(module, "datetime", Frozen)
