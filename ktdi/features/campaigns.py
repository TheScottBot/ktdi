"""Campaigns: an alias ("Monday game") pointing at a D&D Beyond campaign and a VTT, with scheduled reminders."""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands, tasks

from ktdi import common, config, db
from ktdi.common import NO_PINGS, log
from ktdi.lib import reminders

CAMPAIGN_ALIAS_MAX = 50
# Can't be aliases, or !campaign <alias> would clash.
CAMPAIGN_SUBCOMMANDS = {"add", "edit", "list", "remove", "show", "remind", "unremind", "reschedule", "skip"}
# Note: with shared state, aliases must be unique across all shared servers (checked in campaign add / edit).
REMINDER_EMOJI = "🔔"
REMINDER_GRACE = timedelta(hours=1)  # If the bot was down at reminder time, still send it up to this late.
CLEAR_LINK = "none"  # Pass this to /campaign edit to remove a link.
KNOWN_VTTS = {
    "roll20.net": "Roll20",
    "owlbear.rodeo": "Owlbear Rodeo",
    "forge-vtt.com": "The Forge",
    "foundryvtt.com": "Foundry",
    "fantasygrounds.com": "Fantasy Grounds",
    "alchemyrpg.com": "Alchemy",
    "talespire.com": "TaleSpire",
    "dndbeyond.com": "D&D Beyond Maps",
}


# --- Campaign storage ---
@dataclass
class Campaign:
    guild_id: int
    alias: str
    dndbeyond_url: str | None
    vtt_url: str | None
    added_by: int


CAMPAIGN_COLUMNS = "guild_id, alias, dndbeyond_url, vtt_url, added_by"


def get_campaign(guild_id: int, alias: str) -> Campaign | None:
    """Find a campaign this server can see. If two shared servers use the same alias, this server's own wins."""
    where, params = db.scope(guild_id)
    row = db.conn.execute(f"SELECT {CAMPAIGN_COLUMNS} FROM campaigns WHERE {where} AND alias_key = ?"
                          " ORDER BY guild_id = ? DESC, rowid LIMIT 1",
                          (*params, alias.strip().casefold(), guild_id)).fetchone()
    return Campaign(*row) if row else None


def get_campaign_exact(guild_id: int, alias: str) -> Campaign | None:
    """A campaign by the server it was added in (reminders are tied to that)."""
    row = db.conn.execute(f"SELECT {CAMPAIGN_COLUMNS} FROM campaigns WHERE guild_id = ? AND alias_key = ?",
                          (guild_id, alias.strip().casefold())).fetchone()
    return Campaign(*row) if row else None


def list_campaigns(guild_id: int) -> list[Campaign]:
    where, params = db.scope(guild_id)
    rows = db.conn.execute(f"SELECT {CAMPAIGN_COLUMNS} FROM campaigns WHERE {where} ORDER BY alias_key, guild_id != ?",
                           (*params, guild_id)).fetchall()
    return [Campaign(*row) for row in rows]


def save_campaign(guild_id: int, alias: str, dndbeyond_url: str | None, vtt_url: str | None, added_by: int) -> None:
    db.conn.execute(
        "INSERT INTO campaigns (guild_id, alias, alias_key, dndbeyond_url, vtt_url, added_by, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (guild_id, alias, alias.casefold(), dndbeyond_url, vtt_url, added_by,
         datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )
    db.conn.commit()


def update_campaign(guild_id: int, old_alias: str, alias: str, dndbeyond_url: str | None, vtt_url: str | None) -> None:
    db.conn.execute(
        "UPDATE campaigns SET alias = ?, alias_key = ?, dndbeyond_url = ?, vtt_url = ? WHERE guild_id = ? AND alias_key = ?",
        (alias, alias.casefold(), dndbeyond_url, vtt_url, guild_id, old_alias.casefold()),
    )
    # Keep the reminder attached through a rename.
    db.conn.execute("UPDATE campaign_reminders SET alias_key = ? WHERE guild_id = ? AND alias_key = ?",
                    (alias.casefold(), guild_id, old_alias.casefold()))
    db.conn.commit()


def delete_campaign(guild_id: int, alias: str) -> None:
    delete_reminder(guild_id, alias)
    db.conn.execute("DELETE FROM campaigns WHERE guild_id = ? AND alias_key = ?", (guild_id, alias.casefold()))
    db.conn.commit()


# --- Reminder storage. A reminder belongs to its campaign's server, wherever it was set up from. ---
@dataclass
class Reminder:
    id: int
    guild_id: int
    alias_key: str
    channel_id: int
    message_id: int | None
    days: str
    time: str
    every_weeks: int
    anchor: str
    next_run: str
    created_by: int
    lead_minutes: int

    @property
    def schedule(self) -> reminders.Schedule:
        return reminders.Schedule.from_storage(self.days, self.time, self.every_weeks)

    @property
    def next_run_at(self) -> datetime:
        """When the next ping goes out."""
        return datetime.fromisoformat(self.next_run)

    @property
    def lead(self) -> timedelta:
        return timedelta(minutes=self.lead_minutes)

    @property
    def next_game_at(self) -> datetime:
        """The start time the next ping is for."""
        return self.next_run_at + self.lead


REMINDER_COLUMNS = ("id, guild_id, alias_key, channel_id, message_id, days, time, every_weeks, anchor, next_run, "
                    "created_by, lead_minutes")


def get_reminder(guild_id: int, alias: str) -> Reminder | None:
    row = db.conn.execute(f"SELECT {REMINDER_COLUMNS} FROM campaign_reminders WHERE guild_id = ? AND alias_key = ?",
                          (guild_id, alias.casefold())).fetchone()
    return Reminder(*row) if row else None


def reminder_for_message(message_id: int) -> Reminder | None:
    row = db.conn.execute(f"SELECT {REMINDER_COLUMNS} FROM campaign_reminders WHERE message_id = ?",
                          (message_id,)).fetchone()
    return Reminder(*row) if row else None


def due_reminders(now: datetime) -> list[Reminder]:
    rows = db.conn.execute(f"SELECT {REMINDER_COLUMNS} FROM campaign_reminders WHERE next_run <= ?",
                           (now.isoformat(timespec="seconds"),)).fetchall()
    return [Reminder(*row) for row in rows]


def save_reminder(guild_id: int, alias: str, channel_id: int, schedule: reminders.Schedule, anchor: date,
                  next_run: datetime, created_by: int, lead_minutes: int) -> int:
    """Create the campaign's reminder, replacing any existing one (and its subscribers)."""
    delete_reminder(guild_id, alias)
    days, clock, every_weeks = schedule.to_storage()
    cursor = db.conn.execute(
        "INSERT INTO campaign_reminders (guild_id, alias_key, channel_id, days, time, every_weeks, anchor, next_run,"
        " created_by, lead_minutes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (guild_id, alias.casefold(), channel_id, days, clock, every_weeks, anchor.isoformat(),
         next_run.isoformat(timespec="seconds"), created_by, lead_minutes),
    )
    db.conn.commit()
    return cursor.lastrowid


def set_reminder_message(reminder_id: int, message_id: int) -> None:
    db.conn.execute("UPDATE campaign_reminders SET message_id = ? WHERE id = ?", (message_id, reminder_id))
    db.conn.commit()


def update_reminder_schedule(reminder_id: int, schedule: reminders.Schedule, anchor: date, next_run: datetime,
                             lead_minutes: int) -> None:
    """Change when a reminder goes off, keeping its setup message and subscribers."""
    days, clock, every_weeks = schedule.to_storage()
    db.conn.execute("UPDATE campaign_reminders SET days = ?, time = ?, every_weeks = ?, anchor = ?, next_run = ?,"
                    " lead_minutes = ? WHERE id = ?",
                    (days, clock, every_weeks, anchor.isoformat(), next_run.isoformat(timespec="seconds"), lead_minutes,
                     reminder_id))
    db.conn.commit()


def set_next_run(reminder_id: int, next_run: datetime) -> None:
    db.conn.execute("UPDATE campaign_reminders SET next_run = ? WHERE id = ?",
                    (next_run.isoformat(timespec="seconds"), reminder_id))
    db.conn.commit()


def delete_reminder(guild_id: int, alias: str) -> None:
    existing = get_reminder(guild_id, alias)
    if existing:
        db.conn.execute("DELETE FROM campaign_reminder_subscribers WHERE reminder_id = ?", (existing.id,))
        db.conn.execute("DELETE FROM campaign_reminders WHERE id = ?", (existing.id,))
        db.conn.commit()


def subscribe(reminder_id: int, user_id: int) -> None:
    db.conn.execute("INSERT OR IGNORE INTO campaign_reminder_subscribers (reminder_id, user_id) VALUES (?, ?)",
                    (reminder_id, user_id))
    db.conn.commit()


def unsubscribe(reminder_id: int, user_id: int) -> None:
    db.conn.execute("DELETE FROM campaign_reminder_subscribers WHERE reminder_id = ? AND user_id = ?",
                    (reminder_id, user_id))
    db.conn.commit()


def subscribers(reminder_id: int) -> list[int]:
    rows = db.conn.execute("SELECT user_id FROM campaign_reminder_subscribers WHERE reminder_id = ? ORDER BY rowid",
                           (reminder_id,)).fetchall()
    return [row[0] for row in rows]


# --- Links and display ---
class CampaignError(Exception):
    """A problem with what the user typed. The message is safe to show them."""


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def on_domain(url: str, domain: str) -> bool:
    host = host_of(url)
    return host == domain or host.endswith("." + domain)


def vtt_label(url: str) -> str:
    """Name the VTT button after the site where we recognise it, e.g. Roll20. Self-hosted Foundry etc. is just 'VTT'."""
    return next((label for domain, label in KNOWN_VTTS.items() if on_domain(url, domain)), "VTT")


def clean_link(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    link = value.strip().strip("<>")  # People often wrap links in <> to stop Discord previewing them.
    parsed = urlparse(link)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise CampaignError(f"`{value[:100]}` doesn't look like a link. Paste the full address, starting with https://.")
    return link


def sort_links(first: str | None, second: str | None) -> tuple[str | None, str | None]:
    """Work out which link is D&D Beyond and which is the VTT, whichever order they were given in."""
    links = [link for link in (clean_link(first), clean_link(second)) if link]
    dndbeyond = [link for link in links if on_domain(link, "dndbeyond.com") and "/campaigns/" in link]
    others = [link for link in links if link not in dndbeyond]
    if len(dndbeyond) > 1 or len(others) > 1:
        raise CampaignError("Give one D&D Beyond campaign link and one VTT link.")
    return (dndbeyond[0] if dndbeyond else None), (others[0] if others else None)


def ping_phrase(lead_minutes: int) -> str:
    """'pings 15 minutes before' / 'pings at the start time'."""
    return f"pings {reminders.describe_lead(lead_minutes)}"


def when_text(moment: datetime) -> str:
    return f"<t:{int(moment.timestamp())}:F> (<t:{int(moment.timestamp())}:R>)"


def reminder_summary(reminder: Reminder) -> str:
    """e.g. 'Mondays at 19:00, pings 15 minutes before · next ping <in 3 days> · 4 subscribed'."""
    count = len(subscribers(reminder.id))
    next_at = int(reminder.next_run_at.timestamp())
    return (f"⏰ {reminder.schedule.describe()}, {ping_phrase(reminder.lead_minutes)} · "
            f"next ping <t:{next_at}:R> · {count} subscribed")


def campaign_embed(campaign: Campaign) -> discord.Embed:
    lines = []
    if campaign.dndbeyond_url:
        lines.append(f"**D&D Beyond:** {campaign.dndbeyond_url}")
    if campaign.vtt_url:
        lines.append(f"**{vtt_label(campaign.vtt_url)}:** {campaign.vtt_url}")
    reminder = get_reminder(campaign.guild_id, campaign.alias)
    if reminder:
        lines.append(f"**Reminder:** {reminder_summary(reminder)}")
    return discord.Embed(title=f"🎲 {campaign.alias}", description="\n".join(lines), color=discord.Color.dark_red())


def campaign_buttons(campaign: Campaign) -> discord.ui.View:
    view = discord.ui.View(timeout=None)  # Link buttons open the URL directly, so there's nothing to time out.
    if campaign.dndbeyond_url:
        view.add_item(discord.ui.Button(label="D&D Beyond", url=campaign.dndbeyond_url))
    if campaign.vtt_url:
        view.add_item(discord.ui.Button(label=vtt_label(campaign.vtt_url), url=campaign.vtt_url))
    return view


def can_manage_campaign(member: discord.Member, campaign: Campaign) -> bool:
    return member.id == campaign.added_by or member.guild_permissions.manage_messages


def can_manage_reminder(member: discord.Member, reminder: Reminder, campaign: Campaign) -> bool:
    return member.id in (reminder.created_by, campaign.added_by) or member.guild_permissions.manage_messages


def check_alias(alias: str) -> str:
    alias = " ".join(alias.split())  # Tidy stray spaces.
    if not alias:
        raise CampaignError("Give the campaign an alias, like `Monday game`.")
    if len(alias) > CAMPAIGN_ALIAS_MAX:
        raise CampaignError(f"That alias is too long (max {CAMPAIGN_ALIAS_MAX} characters).")
    if alias.casefold() in CAMPAIGN_SUBCOMMANDS:
        raise CampaignError(f"`{alias}` is a command name, so it can't be an alias. Try something like `{alias} game`.")
    if "://" in alias:
        raise CampaignError("The alias goes first, then the links. With `!campaign add`, put a multi-word alias in "
                            "quotes: `!campaign add \"Monday game\" <link> <link>`.")
    return alias


async def send_campaign_reply(ctx: commands.Context, content: str | None = None, campaign: Campaign | None = None,
                              embed: discord.Embed | None = None, private: bool = False) -> None:
    kwargs = {"allowed_mentions": NO_PINGS, "ephemeral": private}
    if campaign:
        kwargs["embed"], kwargs["view"] = campaign_embed(campaign), campaign_buttons(campaign)
    elif embed:
        kwargs["embed"] = embed
    await ctx.send(content, **kwargs)


# --- Scheduling ---
def next_ping(schedule: reminders.Schedule, after: datetime, lead: timedelta, anchor: date | None) -> datetime:
    """The first ping after `after`: the next start time that's more than `lead` away, minus the lead."""
    return reminders.next_occurrence(schedule, after + lead, config.REMINDER_TIMEZONE, anchor) - lead


def plan_schedule(text: str, now: datetime, keep_anchor: date | None = None,
                  keep_lead: int = 0) -> tuple[reminders.Schedule, datetime, date, int]:
    """Parse 'every other monday at 7pm [from 19 oct] [15 minutes before]'.

    Returns (schedule, first ping, anchor, lead minutes). The time in the schedule is the start time.
    """
    tz = config.REMINDER_TIMEZONE
    text, lead_minutes = reminders.split_lead(text)
    lead_minutes = keep_lead if lead_minutes is None else lead_minutes
    lead = timedelta(minutes=lead_minutes)
    schedule_text, start_text = reminders.split_start(text)
    schedule = reminders.parse_schedule(schedule_text)
    if start_text:
        start = reminders.parse_date(start_text, now.astimezone(tz).date())
        game, anchor = reminders.first_on_or_after(schedule, start, now + lead, tz)
    else:
        game = reminders.next_occurrence(schedule, now + lead, tz, keep_anchor)
        anchor = keep_anchor or game.astimezone(tz).date()
    return schedule, game - lead, anchor, lead_minutes


# --- Commands ---
@commands.hybrid_group(name="campaign", description="Our campaigns' D&D Beyond and VTT links, by alias.",
                       invoke_without_command=True)
@commands.guild_only()
async def campaign_group(ctx: commands.Context, *, alias: str = ""):
    # Prefix only: "!campaign Monday game" shows it, "!campaign" lists them all.
    if alias:
        await campaign_show.callback(ctx, alias=alias)
    else:
        await campaign_list.callback(ctx)


@campaign_group.command(name="show", description="Show a campaign's links.")
@app_commands.describe(alias="The campaign's alias, e.g. Monday game")
async def campaign_show(ctx: commands.Context, *, alias: str):
    campaign = get_campaign(ctx.guild.id, alias)
    if campaign is None:
        await send_campaign_reply(ctx, f"There's no campaign called “{discord.utils.escape_markdown(alias)}”. "
                                       "See them all with `/campaign list`.", private=True)
        return
    await send_campaign_reply(ctx, campaign=campaign)


@campaign_group.command(name="list", description="List all our campaigns.")
async def campaign_list(ctx: commands.Context):
    campaigns = list_campaigns(ctx.guild.id)
    if not campaigns:
        await send_campaign_reply(ctx, "No campaigns yet. Add one with `/campaign add`.", private=True)
        return
    lines = []
    for c in campaigns:
        links = [f"[D&D Beyond]({c.dndbeyond_url})"] if c.dndbeyond_url else []
        if c.vtt_url:
            links.append(f"[{vtt_label(c.vtt_url)}]({c.vtt_url})")
        lines.append(f"**{discord.utils.escape_markdown(c.alias)}** · " + " · ".join(links))
        reminder = get_reminder(c.guild_id, c.alias)
        if reminder:
            lines.append(f"  ⏰ {reminder.schedule.describe()}, {ping_phrase(reminder.lead_minutes)} · "
                         f"next ping <t:{int(reminder.next_run_at.timestamp())}:R>")
    embed = discord.Embed(title="🎲 Campaigns", description="\n".join(lines), color=discord.Color.dark_red())
    embed.set_footer(text="Show one with its buttons: /campaign show <alias>")
    await send_campaign_reply(ctx, embed=embed)


@campaign_group.command(name="add", description="Add a campaign: an alias plus its D&D Beyond and/or VTT link.")
@app_commands.describe(alias="Anything that means something to you, e.g. Monday game",
                       dndbeyond="The D&D Beyond campaign link", vtt="The VTT link (Roll20, Foundry, Owlbear…)")
async def campaign_add(ctx: commands.Context, alias: str, dndbeyond: str | None = None, vtt: str | None = None):
    try:
        alias = check_alias(alias)
        dndbeyond, vtt = sort_links(dndbeyond, vtt)
    except CampaignError as error:
        await send_campaign_reply(ctx, str(error), private=True)
        return
    if not dndbeyond and not vtt:
        await send_campaign_reply(ctx, "Add at least one link: the D&D Beyond campaign, the VTT, or both.", private=True)
        return
    if get_campaign(ctx.guild.id, alias):
        await send_campaign_reply(ctx, f"There's already a campaign called “{alias}”. Change it with `/campaign edit`.",
                                  private=True)
        return
    save_campaign(ctx.guild.id, alias, dndbeyond, vtt, ctx.author.id)
    log.info("[%s] %s added campaign %r", ctx.guild.name, ctx.author, alias)
    await send_campaign_reply(ctx, "🎲 Campaign added.", campaign=get_campaign(ctx.guild.id, alias))


@campaign_group.command(name="edit", description="Change a campaign's links or alias (whoever added it, or a mod).")
@app_commands.describe(alias="The campaign to change", dndbeyond=f"New D&D Beyond link, or '{CLEAR_LINK}' to remove it",
                       vtt=f"New VTT link, or '{CLEAR_LINK}' to remove it", rename="A new alias")
async def campaign_edit(ctx: commands.Context, alias: str, dndbeyond: str | None = None, vtt: str | None = None,
                        rename: str | None = None):
    campaign = get_campaign(ctx.guild.id, alias)
    if campaign is None:
        await send_campaign_reply(ctx, f"There's no campaign called “{discord.utils.escape_markdown(alias)}”.", private=True)
        return
    if not can_manage_campaign(ctx.author, campaign):
        await send_campaign_reply(ctx, "Only whoever added this campaign, or a moderator, can change it.", private=True)
        return
    try:
        new_alias = check_alias(rename) if rename else campaign.alias
        new_dndbeyond = None if (dndbeyond or "").strip().lower() == CLEAR_LINK else (clean_link(dndbeyond) or campaign.dndbeyond_url)
        new_vtt = None if (vtt or "").strip().lower() == CLEAR_LINK else (clean_link(vtt) or campaign.vtt_url)
        if new_dndbeyond and not on_domain(new_dndbeyond, "dndbeyond.com"):
            raise CampaignError("That isn't a D&D Beyond link. Put other links in `vtt`.")
    except CampaignError as error:
        await send_campaign_reply(ctx, str(error), private=True)
        return
    if not new_dndbeyond and not new_vtt:
        await send_campaign_reply(ctx, "A campaign needs at least one link. Use `/campaign remove` to delete it.", private=True)
        return
    if new_alias.casefold() != campaign.alias.casefold() and get_campaign(ctx.guild.id, new_alias):
        await send_campaign_reply(ctx, f"There's already a campaign called “{new_alias}”.", private=True)
        return
    update_campaign(campaign.guild_id, campaign.alias, new_alias, new_dndbeyond, new_vtt)
    log.info("[%s] %s edited campaign %r", ctx.guild.name, ctx.author, new_alias)
    await send_campaign_reply(ctx, "✏️ Campaign updated.", campaign=get_campaign_exact(campaign.guild_id, new_alias))


@campaign_group.command(name="remove", description="Remove a campaign (whoever added it, or a mod).")
@app_commands.describe(alias="The campaign to remove")
async def campaign_remove(ctx: commands.Context, *, alias: str):
    campaign = get_campaign(ctx.guild.id, alias)
    if campaign is None:
        await send_campaign_reply(ctx, f"There's no campaign called “{discord.utils.escape_markdown(alias)}”.", private=True)
        return
    if not can_manage_campaign(ctx.author, campaign):
        await send_campaign_reply(ctx, "Only whoever added this campaign, or a moderator, can remove it.", private=True)
        return
    delete_campaign(campaign.guild_id, campaign.alias)
    log.info("[%s] %s removed campaign %r", ctx.guild.name, ctx.author, campaign.alias)
    await send_campaign_reply(ctx, f"🗑️ Removed the campaign “{campaign.alias}”.")


@campaign_group.command(name="remind", description="Remind the group before each session, e.g. mondays at 1900, 15 minutes before.")
@app_commands.describe(alias="The campaign",
                       when="Start time + warning, e.g. mondays at 1900, 15 minutes before · every other friday 7:30pm from 23 oct")
async def campaign_remind(ctx: commands.Context, alias: str, *, when: str):
    campaign = get_campaign(ctx.guild.id, alias)
    if campaign is None:
        await send_campaign_reply(ctx, f"There's no campaign called “{discord.utils.escape_markdown(alias)}”. "
                                       "Add it first with `/campaign add`.", private=True)
        return
    existing = get_reminder(campaign.guild_id, campaign.alias)
    if existing and not can_manage_reminder(ctx.author, existing, campaign):
        await send_campaign_reply(ctx, "This campaign already has a reminder. Only whoever set it, whoever added the "
                                       "campaign, or a moderator can replace it.", private=True)
        return
    now = datetime.now(timezone.utc)
    try:
        schedule, first, anchor, lead_minutes = plan_schedule(when, now)
    except reminders.ScheduleError as error:
        await send_campaign_reply(ctx, str(error), private=True)
        return
    reminder_id = save_reminder(campaign.guild_id, campaign.alias, ctx.channel.id, schedule, anchor, first, ctx.author.id,
                                lead_minutes)
    log.info("[%s] %s set a reminder for %r: %s, %s", ctx.guild.name, ctx.author, campaign.alias,
             schedule.describe(), ping_phrase(lead_minutes))

    tip = "" if lead_minutes else "\n-# Want a heads-up? `/campaign reschedule` it to `15 minutes before`."
    embed = discord.Embed(
        title=f"⏰ Reminder: {campaign.alias}",
        description=(f"**{schedule.describe()}** ({config.REMINDER_TIMEZONE.key} time), {ping_phrase(lead_minutes)}\n"
                     f"First ping: {when_text(first)}{tip}\n\n"
                     f"**React {REMINDER_EMOJI} to this message to get pinged.** Remove your {REMINDER_EMOJI} to stop."),
        color=discord.Color.dark_red(),
    )
    replaced = " It replaces the old one, so react again if you want pings." if existing else ""
    message = await ctx.send(f"⏰ Reminder set.{replaced}", embed=embed, allowed_mentions=NO_PINGS)
    set_reminder_message(reminder_id, message.id)
    try:
        await message.add_reaction(REMINDER_EMOJI)  # So people can just click it.
    except discord.HTTPException:
        pass  # Missing Add Reactions / Read Message History: people can still add 🔔 themselves.


@campaign_group.command(name="unremind", description="Stop a campaign's reminders.")
@app_commands.describe(alias="The campaign")
async def campaign_unremind(ctx: commands.Context, *, alias: str):
    campaign = get_campaign(ctx.guild.id, alias)
    reminder = get_reminder(campaign.guild_id, campaign.alias) if campaign else None
    if campaign is None or reminder is None:
        await send_campaign_reply(ctx, f"“{discord.utils.escape_markdown(alias)}” doesn't have a reminder.", private=True)
        return
    if not can_manage_reminder(ctx.author, reminder, campaign):
        await send_campaign_reply(ctx, "Only whoever set the reminder, whoever added the campaign, or a moderator can "
                                       "stop it. To stop your own pings, remove your 🔔 from the reminder message.",
                                  private=True)
        return
    delete_reminder(campaign.guild_id, campaign.alias)
    log.info("[%s] %s stopped the reminder for %r", ctx.guild.name, ctx.author, campaign.alias)
    await send_campaign_reply(ctx, f"🔕 Stopped the reminders for “{campaign.alias}”.")


async def reminder_to_change(ctx: commands.Context, alias: str) -> tuple[Campaign, Reminder] | None:
    """Look up a campaign's reminder and check the user may change it, replying if not."""
    campaign = get_campaign(ctx.guild.id, alias)
    reminder = get_reminder(campaign.guild_id, campaign.alias) if campaign else None
    if campaign is None or reminder is None:
        await send_campaign_reply(ctx, f"“{discord.utils.escape_markdown(alias)}” doesn't have a reminder. "
                                       "Set one with `/campaign remind`.", private=True)
        return None
    if not can_manage_reminder(ctx.author, reminder, campaign):
        await send_campaign_reply(ctx, "Only whoever set the reminder, whoever added the campaign, or a moderator can "
                                       "change it.", private=True)
        return None
    return campaign, reminder


@campaign_group.command(name="reschedule",
                        description="Change a reminder's schedule, next date or warning, keeping everyone's 🔔.")
@app_commands.describe(alias="The campaign",
                       change="e.g. 30 minutes before · next 26 oct · every other monday 7pm · mondays 6pm from 12 oct")
async def campaign_reschedule(ctx: commands.Context, alias: str, *, change: str):
    found = await reminder_to_change(ctx, alias)
    if found is None:
        return
    campaign, reminder = found
    tz = config.REMINDER_TIMEZONE
    now = datetime.now(timezone.utc)
    anchor = date.fromisoformat(reminder.anchor)
    try:
        rest, new_lead = reminders.split_lead(change)
        lead_minutes = reminder.lead_minutes if new_lead is None else new_lead
        lead = timedelta(minutes=lead_minutes)
        rest = re.sub(r"^(?:and\s+)?(?:remind(?:ers?)?(?:\s+(?:me|us))?|ping|warn(?:ing)?)?\s*", "", rest.strip(), flags=re.I)
        schedule = reminder.schedule
        if not rest:
            # Just the warning, e.g. "30 minutes before": same schedule, same next session.
            if new_lead is None:
                raise reminders.ScheduleError("What should change? e.g. `30 minutes before`, `next 26 oct`, "
                                              "or a new schedule like `every other monday 7pm`.")
            first = reminder.next_game_at - lead
            if first <= now:  # Too late for that session's ping now, so start with the one after.
                first = next_ping(schedule, now, lead, anchor)
        elif rest.lower().startswith("next "):
            # "next 26 oct": same schedule, but the next session (and a fortnightly cadence) moves to that date.
            session = reminders.parse_date(rest[5:], now.astimezone(tz).date())
            if session.weekday() not in schedule.days:
                raise reminders.ScheduleError(f"{session:%A %d %b} isn't on the schedule ({schedule.describe()}). "
                                              "To change the day too, give the full schedule, e.g. "
                                              f"`{'every other ' if schedule.every_weeks > 1 else ''}{session:%A} "
                                              f"at {reminder.time} from {session:%d %b}`.")
            game, anchor = reminders.first_on_or_after(schedule, session, now + lead, tz)
            if game.astimezone(tz).date() != session:
                raise reminders.ScheduleError(f"It's too late for the {session:%d %b} reminder "
                                              f"({ping_phrase(lead_minutes)} {reminder.time}).")
            first = game - lead
        else:
            schedule, first, anchor, lead_minutes = plan_schedule(rest, now, keep_anchor=anchor, keep_lead=lead_minutes)
    except reminders.ScheduleError as error:
        await send_campaign_reply(ctx, str(error), private=True)
        return
    update_reminder_schedule(reminder.id, schedule, anchor, first, lead_minutes)
    log.info("[%s] %s rescheduled the reminder for %r: %s, %s", ctx.guild.name, ctx.author, campaign.alias,
             schedule.describe(), ping_phrase(lead_minutes))
    await send_campaign_reply(ctx, f"🗓️ Reminder for **{campaign.alias}** updated: {schedule.describe()}, "
                                   f"{ping_phrase(lead_minutes)}.\n"
                                   f"Next ping: {when_text(first)}. Everyone's {REMINDER_EMOJI} still counts.")


@campaign_group.command(name="skip", description="Skip the next reminder. Fortnightly games shift a week and carry on from there.")
@app_commands.describe(alias="The campaign")
async def campaign_skip(ctx: commands.Context, *, alias: str):
    found = await reminder_to_change(ctx, alias)
    if found is None:
        return
    campaign, reminder = found
    tz = config.REMINDER_TIMEZONE
    schedule = reminder.schedule
    upcoming = reminder.next_game_at.astimezone(tz)
    if schedule.every_weeks > 1:
        # Push the whole fortnightly cadence back a week, so it stays in step after the skipped week.
        moved = datetime.combine(upcoming.date() + timedelta(days=7), upcoming.time(), tzinfo=tz)
        next_run, anchor = moved.astimezone(timezone.utc) - reminder.lead, moved.date()
        note = "The fortnightly schedule carries on from there."
    else:
        next_run = reminders.next_occurrence(schedule, reminder.next_game_at, tz) - reminder.lead
        anchor = date.fromisoformat(reminder.anchor)
        note = "Back to normal after that."
    update_reminder_schedule(reminder.id, schedule, anchor, next_run, reminder.lead_minutes)
    log.info("[%s] %s skipped a reminder for %r", ctx.guild.name, ctx.author, campaign.alias)
    await send_campaign_reply(ctx, f"⏭️ Skipped the {upcoming:%a %d %b} session for **{campaign.alias}**.\n"
                                   f"Next ping: {when_text(next_run)}. {note}")


async def campaign_alias_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    typed = current.casefold()
    matches = [c.alias for c in list_campaigns(interaction.guild_id) if typed in c.alias.casefold()]
    return [app_commands.Choice(name=alias, value=alias) for alias in matches[:25]]


for _command in (campaign_show, campaign_edit, campaign_remove, campaign_remind, campaign_unremind,
                 campaign_reschedule, campaign_skip):
    _command.autocomplete("alias")(campaign_alias_autocomplete)


# --- Reminder subscriptions (react 🔔) and sending ---
async def reminder_subscribe(payload: discord.RawReactionActionEvent):
    if str(payload.emoji) != REMINDER_EMOJI or payload.user_id == common.bot.user.id:
        return
    reminder = reminder_for_message(payload.message_id)
    if reminder:
        subscribe(reminder.id, payload.user_id)
        log.info("Someone subscribed to reminder %d", reminder.id)


async def reminder_unsubscribe(payload: discord.RawReactionActionEvent):
    if str(payload.emoji) != REMINDER_EMOJI:
        return
    reminder = reminder_for_message(payload.message_id)
    if reminder:
        unsubscribe(reminder.id, payload.user_id)
        log.info("Someone unsubscribed from reminder %d", reminder.id)


async def send_reminder(reminder: Reminder) -> None:
    campaign = get_campaign_exact(reminder.guild_id, reminder.alias_key)
    if campaign is None:
        delete_reminder(reminder.guild_id, reminder.alias_key)
        return
    channel = common.bot.get_channel(reminder.channel_id)
    if channel is None:
        log.warning("Reminder %d: can't find channel %s", reminder.id, reminder.channel_id)
        return
    people = subscribers(reminder.id)
    pings = " ".join(f"<@{user_id}>" for user_id in people)
    start = int(reminder.next_game_at.timestamp())
    if reminder.lead_minutes:
        content = f"⏰ **{campaign.alias}** starts <t:{start}:R> (<t:{start}:t>)! {pings}".strip()
    else:
        content = f"⏰ **{campaign.alias}** is starting now! {pings}".strip()
    if not people:
        content += f"\n-# Nobody's subscribed yet. React {REMINDER_EMOJI} to the reminder setup message to get pinged."
    await channel.send(content, embed=campaign_embed(campaign), view=campaign_buttons(campaign),
                       allowed_mentions=discord.AllowedMentions(users=[discord.Object(id=u) for u in people],
                                                                everyone=False, roles=False))


@tasks.loop(seconds=30)
async def reminder_loop():
    now = datetime.now(timezone.utc)
    for reminder in due_reminders(now):
        try:
            if now - reminder.next_run_at <= REMINDER_GRACE:
                await send_reminder(reminder)
                log.info("Sent reminder %d", reminder.id)
            else:
                log.warning("Skipped reminder %d: it was due at %s, too long ago", reminder.id, reminder.next_run)
        except discord.HTTPException as error:
            log.warning("Couldn't send reminder %d: %s", reminder.id, error)
        finally:
            # Always move on to the next occurrence, so a failure can't cause repeated pings.
            if get_reminder(reminder.guild_id, reminder.alias_key):
                anchor = date.fromisoformat(reminder.anchor)
                set_next_run(reminder.id, next_ping(reminder.schedule, now, reminder.lead, anchor))


@reminder_loop.before_loop
async def before_reminder_loop():
    await common.bot.wait_until_ready()


# --- Help ---
def help_sections() -> list[tuple[str, str, set[str]]]:
    """(title, text, subcommands it's relevant to) for /help campaign and /help campaign <subcommand>."""
    p = config.COMMAND_PREFIX
    return [
        ("📋 Setting up", (
            "• `/campaign add alias:Monday game dndbeyond:<link> vtt:<link>`. The alias can be anything that means "
            "something to you. One link is enough; Roll20, Foundry, Owlbear Rodeo etc. all work as the VTT.\n"
            "• `/campaign show Monday game` gives buttons for D&D Beyond and the VTT. `/campaign list` shows them all.\n"
            f"• `/campaign edit` changes a link (`{CLEAR_LINK}` removes it) or `rename`s the campaign. "
            "`/campaign remove` deletes it, along with its reminder.\n"
            "• Start typing an alias and Discord suggests it."
        ), {"add", "show", "list", "edit", "remove"}),
        ("⏰ Reminders", (
            "• `/campaign remind alias:Monday game when:mondays at 1900, 15 minutes before`\n"
            "• The time is when the game **starts**. The warning is optional: `15m before`, `1h before`, "
            "`half an hour before`, `1 day before`. Without one, it pings at the start time.\n"
            "• Schedules: `monday 7pm`, `mondays and thursdays 19:30`, `weekends 2pm`, `every other friday 7:30pm`. "
            "Add `from 23 oct` to choose when it starts (useful for fortnightly games).\n"
            f"• React {REMINDER_EMOJI} to the message it posts to get pinged; remove your {REMINDER_EMOJI} to stop. "
            "Reminders include the campaign's buttons.\n"
            f"• One reminder per campaign. `/campaign unremind` stops it; a new `/campaign remind` replaces it "
            f"(and everyone needs to {REMINDER_EMOJI} again).\n"
            f"• Times are {config.REMINDER_TIMEZONE.key} time; summer time is handled."
        ), {"remind", "unremind"}),
        ("🗓️ When the game moves", (
            "• `/campaign skip`: skip the next session. Fortnightly games shift a week and carry on from there.\n"
            "• `/campaign reschedule change:next 26 oct`: the next session is on that date (a fortnightly "
            "schedule counts from it).\n"
            "• `change:30 minutes before`: change just the warning.\n"
            "• `change:every other thursday 8pm from 5 nov`: a whole new schedule.\n"
            f"• All of these keep everyone's {REMINDER_EMOJI}."
        ), {"skip", "reschedule", "remind"}),
        ("🔐 Who can change what", (
            f"• Anyone can add a campaign, and anyone can {REMINDER_EMOJI} to get pinged.\n"
            "• Editing or removing a campaign: whoever added it, or anyone with Manage Messages.\n"
            "• Changing, skipping or stopping a reminder: whoever set it, whoever added the campaign, or a mod."
        ), {"edit", "remove", "remind", "unremind", "skip", "reschedule"}),
        (f"⌨️ Typing it with {p}", (
            f"• `{p}campaign Monday game` shows one; `{p}campaign` lists them all.\n"
            "• When more follows the alias, put a multi-word alias in quotes: "
            f"`{p}campaign add \"Monday game\" <link> <link>`, "
            f"`{p}campaign remind \"Monday game\" mondays at 1900, 15m before`, "
            f"`{p}campaign reschedule \"Monday game\" next 26 oct`.\n"
            f"• `{p}campaign skip Monday game` and `{p}campaign remove Monday game` don't need quotes."
        ), {"add", "show", "list", "edit", "remove", "remind", "unremind", "skip", "reschedule"}),
    ]


def help_extras(command: commands.Command) -> tuple[str, list[tuple[str, str, bool]]]:
    parent = command.parent.name if command.parent else None
    if command.name == "campaign":
        return ("\n-# For one command in detail: `/help campaign remind`, `/help campaign reschedule`…",
                [(title, text, False) for title, text, _ in help_sections()])
    if parent == "campaign":
        return "", [(title, text, False) for title, text, subs in help_sections() if command.name in subs]
    return "", []


async def setup(bot: commands.Bot):
    bot.add_command(campaign_group)
    bot.add_listener(reminder_subscribe, "on_raw_reaction_add")
    bot.add_listener(reminder_unsubscribe, "on_raw_reaction_remove")
    reminder_loop.start()


async def teardown(bot: commands.Bot):
    reminder_loop.cancel()
