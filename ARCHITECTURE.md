# KTDI architecture and design

How the bot is put together, why, and the rules to follow when changing it. Written for anyone making changes. The [README](README.md) covers what the commands do for users; this covers how they work.

**Before changing anything:** read [Rules for changes](#rules-for-changes) and run the tests (`python -m pytest`).

---

## 1. What it is

A Discord bot for a group of friends who play D&D together, mostly in voice chat. It lives on a few servers (one
"hangout" server that serves three campaigns, plus others), and is deliberately small and personal: in-jokes
(spray, blame, `/linux`, `/anime`), quotes from game night, campaign links and session reminders, a private book
library, and two unit converters.

It is run by one person on a homelab, so it favours: simple deployment, few external services (Discord, plus the
optional Calibre-Web, and AniList's free public API for `/anime`), a single SQLite file, and failing gracefully over
failing loudly. Anything that calls an outside service must keep working, or say so nicely, when it's down.

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
│   ├── fun.py         spray, whospray, tdoi, loot, bad, toenoyoudidnt, linux, blame, bribe, expunge, bail, rapsheet, 💦, Champion Briber
│   ├── futures.py     /sprayfutures, /sprayrate: bets on someone being sprayed; settled by fun.after_spray or expiry_loop
│   ├── committee.py   /committee: the committee's funds (bribes in, spending out)
│   ├── anime.py       /anime (asks ANIME_USER_ID about a random AniList anime)
│   ├── movie.py       movie night: /np, /shhh, /rate, /predict, /bingo (✅/❌ judging listener)
│   ├── units.py       /abm, /imperial
│   ├── timezones.py   /timezone (convert, set, show, clear); parsing lives in lib/timezones.py
│   ├── quotes.py      quotes (prefix group, slash group, right-click form)
│   ├── campaigns.py   campaigns, reminders, the reminder loop
│   ├── settings.py    /settings (shared state, whospray user)
│   ├── books.py       /books (Calibre-Web)
│   ├── rpg.py         /rpg (RPG rulebooks in a Dropbox folder; download links)
│   └── help.py        /help
└── lib/               plain Python, no Discord imports
    ├── abm.py         unit parsing and conversion (+ abm_units.json dataset)
    ├── reminders.py   schedule parsing, dates, warnings, next-occurrence maths
    ├── library.py     Calibre-Web OPDS client
    ├── dropbox.py     Dropbox API client for /rpg: refresh-token login, folder listing, temporary links
    ├── anilist.py     random popular anime from AniList
    ├── timezones.py   timezone and time parsing for /timezone
    └── letterboxd.py  reads public Letterboxd list and film pages (no open API); only letterboxd.com/boxd.it URLs
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

`fun.recent_speakers` and `fun.last_blame` (blame and bribe work per channel and are meant to be ephemeral), and
`books.recent_books` (a cache so `/books download <id>` knows
formats and sizes).

## 6. /help

`/help` is built from the registered prefix commands and printed with a `/`. Features extend it without `help.py`
changing:

- `help_extras(command) -> (extra description, [(field name, text, inline), ...])`: detail for `/help <command>`
  and `/help <group> <subcommand>`. Return `("", [])` for commands that aren't yours.
- `HELP_CATEGORY = "🎲 Fun"`: where the feature's commands sit on the main `/help` list. One command can differ with
  `extras={"category": ...}` (`/loot` and `/linux` are 🎲 Fun, the rest of `fun.py` is 💦 Rap sheet). Categories are
  shown in `help.CATEGORY_ORDER`, and a new one goes after those; a command with no category lands in 🧩 Other, which
  a test refuses.
- `main_help_lines() -> [(category, line)]`: extra lines on the main list for things that aren't commands (e.g. 💦).
- Command `extras`:
  - `"prefix_only": True` → shown as `!quote anon`, left out of the `/…` summary.
  - `"available": fn(guild) -> bool` → hidden from `/help`, and not synced as a slash command, where it can't be
    used (`/books`, `/rpg`).
  - `"configured": fn() -> bool` → not synced at all when the feature isn't set up on this bot (`KTDIBot.unavailable_commands`).
  - `"private": True` → never logged with who used it (see §9).
  - `"hidden": True` → a cryptid: left off the main `/help` list, though `/help <name>` still works. Make it a plain
    `commands.command` (`!`-only) too, as `!toenoyoudidnt` is: Discord's slash menu shows every slash command, and a
    bot can't hide one from it. `/help` titles `!`-only commands with `!`.
- If a prefix command's arguments are in a different order to its slash version, set `usage=` to the slash form
  (e.g. `quote add`).

**Discord limits** (Discord rejects the *whole* message if exceeded): embed field value 1024 characters, embed total
6000, 25 fields. `help.add_help_field()` / `fit_embed()` trim and log instead of failing, and
`tests/test_registration.py` checks every help page. Split long help into several topic fields, as campaigns does.

The main list is one field per category, one line per command. A category over 1024 characters carries on in a
"(cont.)" field, and if the fields outgrow one embed, `help.paginate()` spreads them over pages with ◀ / ▶ buttons
(`HelpPages`, only the person who asked can flip them). Today it's one page (6 fields, ~1,700 characters), so the
buttons don't appear; tests force pagination to keep that path working.

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
| `bad_counts` | times each person was told off with `/bad @them`, per (server, person). Its own rap sheet line; not a spray. |
| `spray_expunges` | sprays each person paid to remove (`/expunge`), per (server, person). Subtracted from sprays on read; sprays are never deleted. |
| `spray_bails` | sprays removed from someone's record by someone else (`/bail`), per (server, person, payer). Also subtracted on read. |
| `movies` | one row per **watch** of a film: title (and `title_key`, casefolded, to match rewatches), who set it, started/paused/ended times, seconds paused, `watch_number` (fixed at `/np start`, counting earlier watches through `scope()`), `archived_at` for the watchlist (the to-watch list: added, imported from Letterboxd, or set aside unstarted), `link` (its Letterboxd page), `dropped_at` (taken off the watchlist; kept) and `struck_at` (struck off as watched: still listed, crossed out, left out of random votes) and `from_watchlist` (lined up from the watchlist: when that watch ends, `keep_on_watchlist_struck()` adds a fresh struck entry, since the watch's own row keeps its ratings and predictions). A server's current film is its row that's neither ended nor archived; that and the watchlist are per server, never shared. `/np history` and `/np predictions` read through `scope()`. Nothing is deleted: a film swapped or ended before it starts is archived, predictions and all, and `/np set` of the same title restores it. |
| `movie_votes` / `movie_vote_options` | `/np vote`: the Discord poll's message, and which poll answer (1, 2, 3...) is which watchlist film. The votes themselves stay in Discord; the bot reads them when the poll closes (`/np vote end`, or the "poll results" message Discord posts when its time runs out). One open vote per server. |
| `movie_ratings` | `/rate` scores, per (movie, person) |
| `movie_predictions` / `movie_prediction_votes` | sealed `/predict`ions, each tied to its film by `movie_id`. `message_id` is set when `/np end` reveals them, and ✅/❌ reactions on that message are the votes (called it if ✅ > ❌). Only revealed ones are ever shown (`/np predictions`, rap sheets); archived films keep theirs, still sealed. |
| `movie_bingo_marks` / `movie_bingo_wins` | squares marked and wins. Cards aren't stored: `movie.bingo_card()` shuffles the squares with a seed of (movie, person). |
| `user_timezones` | each person's own timezone (`/timezone set`), per person, not per server: an IANA name or a fixed offset like `UTC+5:30`. Logged as "set their timezone", never which one. |
| `spray_futures` | `/sprayfutures` bets: who bet on whom, the stake, `hours`, the day's `rate` and the `amount` on the line (stake × hours plus interest, fixed when placed), when it expires, and how it settled (`outcome` won/lost, `paid` on a win, capped so a record never goes below zero, and `sprayed_by`, never the bettor). Lost amounts and paid winnings are part of `fun.get_spray_count`. Every spray goes through `fun.after_spray`, which pays out open bets on the target; `futures.expiry_loop` settles the rest as lost. |
| `spray_rates` | the daily spray interest rate (1-20%), one row per day: picked at random the first time it's needed after `SPRAY_RATE_TIME` (in `BOT_TIMEZONE`). Bot-wide, so no `guild_id`. |
| `committee_spending` | what the committee's money was spent on (`/committee spend`): amount, item, who. Money in isn't stored separately: it's the `bribes` totals (bribe, expunge and bail all record a bribe), so the balance is bribes minus spending, both read through `scope()`. |

### Rules

- **Every row records the server it came from (`guild_id`).** Never move or copy rows between servers. The two
  exceptions: `user_timezones` (a person's timezone is about them, not a server, so it follows them everywhere, and
  only exists if they set it) and `spray_rates` (one daily rate for the whole bot).
- **Reads go through `db.scope(guild_id)`**, which returns a `WHERE` condition + parameters (see §8). Writes always
  record the server the command ran in.
- **Changes to an existing row target that row's own server**: e.g. editing a campaign uses `campaign.guild_id`, not
  `ctx.guild.id`. Reminders belong to their campaign's server (`get_campaign_exact`), even if set up from another.
- **Counters are summed on read** (`SUM(count)` across the servers in scope), not stored pooled. Removals are
  recorded as their own counter and subtracted (sprays minus expunges minus bails, plus lost spray futures minus won ones), so nothing is ever deleted from another
  server's rows.
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
- **`/rpg` gets the same treatment**: no user, search text, rulebook name or number. `DropboxError(private=True)` marks
  errors that name a file. Only the size of a sent link is logged. `tests/test_rpg.py` checks the logs.
- **Dissociating a quote doesn't log who asked**, since that would reveal whose quote it was. Saving a quote logs who
  saved it, not who said it.
- Replies never ping unexpectedly: quote and campaign replies use `NO_PINGS`; reminders ping only subscribers and
  never @everyone.

## 10. Reminders

- **The time in a schedule is when the game starts.** `lead_minutes` is the optional warning; the ping goes at
  start − lead. `Reminder.next_run_at` is the ping; `next_game_at` is the session it's for.
- Times are in `config.REMINDER_TIMEZONE` (defaults to `config.BOT_TIMEZONE`, the bot's own timezone, which defaults
  to Europe/London and is also `/timezone convert`'s fallback). Always build local times with `zoneinfo` so summer
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
- **`dropbox.py`**: swaps the refresh token for short-lived access tokens (and retries once on a 401), lists the folder
  recursively (cached 10 minutes), searches it by words in the path, and makes 4-hour temporary links. Only for files
  in its own listing, so nothing outside the folder can be fetched. `ktdi/tools/dropbox_login.py` gets the token.
- **`anilist.py`**: `random_anime()` picks one of AniList's 500 most popular non-adult anime (GraphQL, no key needed,
  10 s timeout). It never raises: if AniList is unreachable it picks from `FALLBACK_TITLES`. Tests never call the
  real API; they fake `random_anime` or point `API_URL` at a closed port.

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
  every `/help` page, including the main list, fits Discord's limits. Update its expected lists when you add commands.
- `test_books.py` runs a fake Calibre-Web with aiohttp; `test_rpg.py` runs a fake Dropbox.

## Rules for changes

1. **Run the tests before and after.** Add tests for new behaviour in the matching `tests/test_<feature>.py`.
2. **New feature** → new `ktdi/features/<name>.py` with `setup(bot)`, add it to `FEATURES`, optionally `help_extras`.
   New settings go in `config.py` and `.env.example`.
3. **Help and README stay accurate.** Command descriptions appear in `/help` automatically; anything that isn't a
   command (reactions, extra tips) needs `help_extras` / `main_help_lines`. Give new features a `HELP_CATEGORY`. Update the README command table.
4. **Data:** reads through `db.scope()`, writes record the current server, edits target the row's own server,
   schema changes are additive upgrades in `db._upgrade()`.
5. **Privacy:** nothing about `/books` or `/rpg` use may be logged against a person. Don't add logging that reveals what a
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
| `/rpg` sends Dropbox links, not files | Rulebooks are usually 50–300 MB, far over Discord's upload limit. Links last 4 hours. |
| Root `bot.py` launcher kept | The systemd service never needs editing. |
