# KTDI architecture and design

How the bot is put together, why, and the rules to follow when changing it. Written for anyone making changes. The [README](README.md) covers what the commands do for users; this covers how they work.

**Before changing anything:** read [Rules for changes](#rules-for-changes) and run the tests (`python -m pytest`).

---

## 1. What it is

A Discord bot for a group of friends who play D&D together, mostly in voice chat. It lives on a few servers (one
"hangout" server that serves three campaigns, plus others), and is deliberately small and personal: in-jokes
(spray, blame, `/linux`), quotes from game night, campaign links and session reminders, a private book library, and
two unit converters.

It is run by one person on a homelab, so it favours: simple deployment, no external services beyond Discord (and an
optional Calibre-Web), a single SQLite file, and failing gracefully over failing loudly.

## 2. Runtime and deployment

| Thing | Where |
|---|---|
| Code | `/opt/ktdi` in a Proxmox container, a git checkout |
| Service | systemd `ktdi.service`: `WorkingDirectory=/opt/ktdi`, `ExecStart=/opt/ktdi/.venv/bin/python /opt/ktdi/bot.py`, restarts on failure |
| Settings | `/opt/ktdi/.env` (see `.env.example`); `.env.dev` for the dev bot (`python bot.py --dev`) |
| Data | `/opt/ktdi/ktdi.db` (SQLite), backed up nightly by the homelab. Copy it with SQLite's backup API (a consistent snapshot), never plain `cp` while the bot is running. |
| Logs | `/opt/ktdi/logs/ktdi.log` (rotating, 1 MB × 5) and the systemd journal |

Deploying is `git pull` + `systemctl restart ktdi`. `pip install -e .` is only needed when `pyproject.toml` changes
(dependencies, entry points). Slash commands are re-registered to the servers in `GUILD_IDS` on every start.

The root `bot.py` is a six-line launcher kept so the service's start command never has to change. `python -m ktdi`
and the `ktdi` command do the same thing.

**Never run the bot locally with the live token while the homelab one is running.** Two processes on one token both
receive every event, fight over slash command registration, and cause "Unknown interaction" / missing command bugs.
Use a separate dev bot application with `.env.dev`.

## 3. Layout

```
bot.py                 launcher
ktdi/
├── bot.py             KTDIBot: startup, loading features, syncing slash commands, command logging, errors
├── config.py          every setting from .env, in one place
├── db.py              SQLite connection, schema, upgrades, shared state (scope())
├── common.py          helpers shared by features (Reply, send_reply/respond, NO_PINGS, get_member, common.bot)
├── features/          one file per feature; each is a discord.py extension
│   ├── __init__.py    FEATURES: the load order
│   ├── fun.py         spray, whospray, tdoi, loot, linux, blame, bribe, rapsheet, 💦 reaction, Champion Briber role
│   ├── units.py       /abm, /imperial
│   ├── quotes.py      quotes (prefix group, slash group, right-click form)
│   ├── campaigns.py   campaigns, reminders, the reminder loop
│   ├── settings.py    /settings (shared state, whospray user)
│   ├── books.py       /books (Calibre-Web)
│   └── help.py        /help
└── lib/               plain Python, no Discord imports
    ├── abm.py         unit parsing and conversion (+ abm_units.json dataset)
    ├── reminders.py   schedule parsing, dates, warnings, next-occurrence maths
    └── library.py     Calibre-Web OPDS client
tests/                 pytest; fakes.py has stand-ins for Discord objects
```

**Dependency direction:** `lib` depends on nothing in `ktdi`. `features` depend on `config`, `db`, `common`, `lib`.
`bot.py` depends on `features/__init__.py` (the list) only. Features should not import each other, except `help`,
which only calls the optional hooks described in §6.

## 4. Startup

1. `bot.py` → `ktdi.bot.main()`.
2. `config` loads `.env` (or `.env.dev` with `--dev`) at import.
3. `create_bot()`: `db.init(DB_PATH)` creates missing tables and runs upgrades, loads shared-state settings;
   creates `KTDIBot` and stores it in `common.bot`.
4. `setup_hook()` (after login, before gateway connect):
   - loads every extension in `FEATURES` (each `setup(bot)` registers its commands, listeners and loops);
   - for each server in `GUILD_IDS`: copies global commands to that server, removes `/books` where the library isn't
     available, syncs; then clears global commands so nothing appears twice. With no `GUILD_IDS`, syncs globally.
5. `on_ready` logs `Logged in as …`.

Server-only registration (`GUILD_IDS`) is deliberate: global slash command changes can take a long time to reach
clients; per-server changes are instant.

## 5. Features

Each feature file is a discord.py **extension**: commands are module-level functions, and `async def setup(bot)` at
the bottom registers them (`bot.add_command`, `bot.tree.add_command`, `bot.add_listener`, `loop.start()`).
Extensions were chosen over Cog classes so commands stay plain functions that tests can call directly
(`run(quotes.quote_slash_add.callback(interaction, ...))`).

### Command styles

- **Hybrid commands** (`@commands.hybrid_command` / `hybrid_group`) are the default: one function serves `/spray` and
  `!spray`. Use `ctx.send(..., ephemeral=True)` for private replies; it is ignored for `!` commands, which can't be
  private.
- **Separate prefix and slash versions** are used when they need different arguments. Quotes do this: `!quote` parses
  replies, `@mentions` and free text itself, while `/quote add` has typed options. Both call the same action
  functions (`save_quote`, `show_quote`…), which return a `Reply` that `send_reply()` / `respond()` deliver.
- **Right-click message commands** (`app_commands.context_menu`) with a `discord.ui.Modal` form: "Save quote".
- **Prefix group roots** can take free text (`!quote @Dave text`, `!campaign Monday game`); the slash side only has
  subcommands.

### Background work and events

- Listeners: `on_message` (blame's recent speakers), `on_raw_reaction_add` (💦 spray, 🔔 subscribe),
  `on_raw_reaction_remove` (🔔 unsubscribe). Use the `raw_` events so reactions on messages from before a restart
  still count.
- `campaigns.reminder_loop` runs every 30 seconds.
- Code with no `ctx` to hand uses `common.bot` (the running bot) for `get_channel`, `user`, `guilds`.

### In-memory state (lost on restart, by design)

`fun.recent_speakers` and `fun.last_blame` (blame and bribe work per channel and are meant to be ephemeral) and
`books.recent_books` (a cache so `/books download <id>` knows formats and sizes).

## 6. /help

`/help` is built from the registered prefix commands and printed with a `/`. Features extend it without `help.py`
changing:

- `help_extras(command) -> (extra description, [(field name, text, inline), ...])`: detail for `/help <command>`
  and `/help <group> <subcommand>`. Return `("", [])` for commands that aren't yours.
- `main_help_fields() -> [(name, text)]`: extra lines on the main list for things that aren't commands (e.g. 💦).
- Command `extras`:
  - `"prefix_only": True` → shown as `!quote anon`, left out of the `/…` summary.
  - `"available": fn(guild) -> bool` → hidden from `/help` where it can't be used (`/books`).
  - `"private": True` → never logged with who used it (see §9).
- If a prefix command's arguments are in a different order to its slash version, set `usage=` to the slash form
  (e.g. `quote add`).

**Discord limits** (Discord rejects the *whole* message if exceeded): embed field value 1024 characters, embed total
6000, 25 fields. `help.add_help_field()` / `fit_embed()` trim and log instead of failing, and
`tests/test_registration.py` checks every help page. Split long help into several topic fields, as campaigns does.

## 7. Data

One SQLite file, opened once (`db.conn`). Schema lives in `db.SCHEMA`; changes to existing tables go in
`db._upgrade()`.

| Table | Holds |
|---|---|
| `sprays` | spray count per (server, person) |
| `bribes` | bribe count and total per (server, person) |
| `briber_role_holders` | who holds the Champion Briber role, per server |
| `quotes` | quotes; `user_id = 0` means anonymous; `message_id` links to the original (dropped for anonymous) |
| `campaigns` | alias → D&D Beyond / VTT links, per server; `alias_key` is the lowercased alias |
| `campaign_reminders` | one per campaign: schedule, start time, `lead_minutes`, `next_run`, setup message |
| `campaign_reminder_subscribers` | who reacted 🔔 to a reminder |
| `guild_settings` | per-server settings: shared state, and the Don (`whospray_user_id`: who `/whospray` asks and `/tdoi` obeys). Never shared between servers. |
| `don_orders` | times each person sprayed themselves on the Don's orders (`/tdoi`), per (server, person) |

### Rules

- **Every row records the server it came from (`guild_id`).** Never move or copy rows between servers.
- **Reads go through `db.scope(guild_id)`**, which returns a `WHERE` condition + parameters (see §8). Writes always
  record the server the command ran in.
- **Changes to an existing row target that row's own server**: e.g. editing a campaign uses `campaign.guild_id`, not
  `ctx.guild.id`. Reminders belong to their campaign's server (`get_campaign_exact`), even if set up from another.
- **Counters are summed on read** (`SUM(count)` across the servers in scope), not stored pooled.
- **Upgrades are additive**: add columns with defaults that keep old behaviour (e.g. `lead_minutes DEFAULT 0` kept old
  reminders pinging at their old time). Never drop or rewrite data in an upgrade. `db.init()` must work on any older
  database.
- SQL placeholders (`?`) for every value. `scope()` only ever produces fixed text with `?`, so f-string-ing its
  condition in is safe; never f-string user input.
- Quote IDs are global (autoincrement), so `#12` is the same quote on every server that can see it.

## 8. Shared state

Per-server setting, stored in `guild_settings`; a server with no row counts as **shared**. Changed with
`/settings shared_state` (needs Manage Server).

```python
db.scope(guild_id):
    isolated server            -> "guild_id = ?",          [this server]
    shared, nobody isolated    -> "1 = 1",                  []
    shared, some isolated      -> "guild_id NOT IN (?, ?)", [the isolated servers]
```

Covers quotes, sprays (including Don orders), bribes and campaigns. Not books (per `BOOKS_GUILD_IDS`), not roles (each server gives out its
own Champion Briber role), not blame/bribe state (per channel, in memory). Switching is reversible because nothing
moves; only the condition changes. Campaign aliases must be unique across the servers in scope; lookups prefer the
asking server's own row.

## 9. Logging and privacy

Everything logs through `logging.getLogger("ktdi")` (`common.log`) to the file and the journal.

- Every command is logged with who ran it and what they typed (`KTDIBot.on_command`), **except** commands whose root
  has `extras["private"]`.
- **`/books` is never logged against a person**: no user, search text, title or book ID. `LibraryError(private=True)`
  marks errors that name a book; log `error.log_text`, never `str(error)`. aiohttp errors are reduced to their type,
  because their messages can contain the request URL. `tests/test_books.py` checks the logs.
- **Dissociating a quote doesn't log who asked**, since that would reveal whose quote it was. Saving a quote logs who
  saved it, not who said it.
- Replies never ping unexpectedly: quote and campaign replies use `NO_PINGS`; reminders ping only subscribers and
  never @everyone.

## 10. Reminders

- **The time in a schedule is when the game starts.** `lead_minutes` is the optional warning; the ping goes at
  start − lead. `Reminder.next_run_at` is the ping; `next_game_at` is the session it's for.
- Times are in `config.REMINDER_TIMEZONE` (default Europe/London). Always build local times with `zoneinfo` so summer
  time is handled; store UTC ISO strings.
- **Fortnightly** schedules have an `anchor` date: its week is an "on" week. `from <date>` sets it; `skip` on a
  fortnightly game moves the whole cadence a week (the anchor moves); `reschedule next <date>` re-anchors.
- The loop sends anything due, up to `REMINDER_GRACE` (1 hour) late, then **always** moves `next_run` on, so a failure
  can't cause repeated pings.
- Subscribing is a 🔔 reaction on the setup message (`reminder_for_message`). Replacing a reminder with a new
  `/campaign remind` resets subscribers; `reschedule` and `skip` keep them.
- All parsing and date maths live in `ktdi/lib/reminders.py` and are tested without Discord.

## 11. Libraries (`ktdi/lib`)

- **`abm.py`**: parses metric input (`3cm`, `20C`, `100 km/h`) into a dimension + SI value, then either picks an
  absurd unit from `abm_units.json` (`convert`) or converts sincerely (`to_imperial`). To add absurd units, add
  entries to the JSON (`id`, `name`, `plural`, `dimension`, `si_value`, `accuracy`, optional `article`); to add input
  units, `_add(...)` in `abm.py`. Temperature compares in kelvin; decibels compare to the nearest reference point.
- **`reminders.py`**: `parse_schedule`, `split_lead`, `split_start`, `parse_date`, `next_occurrence`,
  `first_on_or_after`, `describe*`. Raises `ScheduleError` with user-safe messages.
- **`library.py`**: Calibre-Web OPDS search (follows pagination) and download (prefers formats in order, respects
  Discord's upload limit). Basic auth is built by hand (aiohttp's `BasicAuth` is deprecated).

## 12. Tone and content

- The humour is the group's in-jokes and absurd comparisons. **Never mock America, imperial units or Fahrenheit**; 
    American reference points in `/abm` are fine because they're genuinely useful.
  `/imperial` is sincere and signs off with ❤️.
- Error and refusal messages are friendly, say what to do instead, and are private (`ephemeral`) where possible.
- British English in user-facing text.

## 13. Testing

```bash
pip install -e ".[dev]"
python -m pytest            # ~3 seconds
```

- `tests/conftest.py` gives every test a fresh in-memory database, a `FakeBot` in `common.bot`, and never reads the
  real `.env` (`KTDI_NO_DOTENV=1`).
- `tests/fakes.py`: `User`, `Guild`, `Channel`, `Message`, `Ctx` (`slash=True/False`), `Interaction`, `FrozenClock`.
  Call commands directly: `run(feature.command.callback(ctx, ...))`; check `ctx.last.content`, `.embed`, `.private`.
- Freeze time with the `clock` fixture: `clock.set(datetime(...), campaigns)` patches that module's `datetime.now()`.
- `test_registration.py` loads every feature onto a real `KTDIBot` and checks the command list, listeners and that
  every `/help` page fits Discord's limits. Update its expected lists when you add commands.
- `test_books.py` runs a fake Calibre-Web with aiohttp.

## Rules for changes

1. **Run the tests before and after.** Add tests for new behaviour in the matching `tests/test_<feature>.py`.
2. **New feature** → new `ktdi/features/<name>.py` with `setup(bot)`, add it to `FEATURES`, optionally `help_extras`.
   New settings go in `config.py` and `.env.example`.
3. **Help and README stay accurate.** Command descriptions appear in `/help` automatically; anything that isn't a
   command (reactions, extra tips) needs `help_extras` / `main_help_fields`. Update the README command table.
4. **Data:** reads through `db.scope()`, writes record the current server, edits target the row's own server,
   schema changes are additive upgrades in `db._upgrade()`.
5. **Privacy:** nothing about `/books` use may be logged against a person. Don't add logging that reveals what a
   dissociated/anonymous action was meant to hide.
6. **Discord limits:** slash command and option descriptions ≤ 100 characters, ≤ 25 options/choices/autocomplete
   results, embed fields ≤ 1024, embeds ≤ 6000, uploads 10 MB on unboosted servers, and a reply to a slash command
   within 3 seconds (call `ctx.defer()` first if it may be slower).
7. **Don't break the start command.** `python /opt/ktdi/bot.py` must keep working; don't move `.env`, `ktdi.db` or
   `logs/` without updating deployment.
8. **Permissions pattern:** people can change what they created; whoever it's about can change it where that makes
   sense (quotes); `manage_messages` (mods) can change anything; server settings need `manage_guild`, except choosing the Don, which only the user IDs in `WHOSPRAY_ADMIN_IDS` (`.env`) can do.
9. **Commits are made by the maintainer.** Assistants make and verify changes; they don't commit or push.

## Decisions and their reasons

| Decision | Why |
|---|---|
| Extensions, not Cog classes | Plain functions are easy to test and moved over unchanged; same one-file-per-feature split. |
| Hybrid commands by default | One implementation for `/` and `!`; people use both. |
| Quotes split into prefix and slash versions | `!quote` needs to read replies and free text; `/quote` needs typed options. |
| Server-only slash registration | Instant updates; global registration was slow and caused confusing stale commands. |
| One SQLite file, `guild_id` on every row | Simple backups; makes shared state a read-time `WHERE` instead of data migration. |
| Shared state on by default, stored in the DB | The maintainer's servers are meant to share; per-server rows mean no second source of truth in `.env`. |
| Blame/bribe state in memory | It's a per-channel, in-the-moment joke; persisting it adds complexity for no benefit. |
| One reminder per campaign; warnings as `lead_minutes` | Matches how the group plays; the schedule stays "when the game starts". |
| `/books` private and unlogged | People shouldn't feel watched for what they read. |
| Root `bot.py` launcher kept | The systemd service never needs editing. |
