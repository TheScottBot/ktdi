# ktdi
Keep The Degenerates Inline

A tiny Discord bot for keeping your friends in line. Commands work as slash commands (`/spray`) and as text commands using a configurable prefix (`!spray` by default; set `COMMAND_PREFIX` in `.env`).

| Command | What it does |
|---|---|
| `spray [@user]` | Posts a spray bottle GIF. Target someone to add to their rap sheet. |
| `whospray` | Asks the server's Don (set with `/settings whospray_user`) who should be sprayed, with a random phrase. Only the Don is pinged. |
| `tdoi` | The Don Ordered It: sprays yourself, on the Don's orders. Counts as a spray, and as a separate "sprayed themselves on the Don's orders" count on your rap sheet. |
| `np set <title>` / `np start` / `np countdown` / `np elapsed` / `np pause [reason]` / `np resume` / `np end` | Movie night. `set` lines a film up without starting it (so people can predict and get their bingo cards); `start` starts it and sets the bot's status to "Watching …"; `countdown` posts a live Discord timestamp ("starts in 5 seconds") that counts itself down on everyone's screen to the same moment, then changes to GO and starts it, so everyone presses play together; pauses don't count towards the time watched (pause over 5 minutes and the committee notices). `end` reveals the predictions and asks for ratings. Start, resume and `/np` show a live clock Discord keeps ticking ("⏱️ Started 47 minutes ago", not counting pauses); pause and resume give the exact spot (`0:47:12`) so everyone can line up. `np elapsed` (only you see it) gives the exact spot now plus a catch-up point: "skip to 0:47:22, pause, and press play in 10 seconds", so someone who paused on their own can rejoin in sync. `/np` on its own shows what's on and how far in; `np history` lists what you've watched with ratings and how many predictions were called; `np predictions [title]` shows what was predicted for a film (e.g. `/np predictions Alien`, or `Alien #1` for the first watch; it autocompletes) and who called it. Watching a film again is a new numbered watch ("Alien (watch #2)") with its own predictions, bingo cards and ratings. |
| `np watchlist` | Films that were lined up but never started: changing the film with `np set` before it starts, or `np end`ing it unstarted, saves it here (not yet watched) with its sealed predictions. `np set` the same title (it autocompletes from the watchlist) to bring it back, predictions and all. |
| `rate [1-10]` | Rate the film that's on, or the last one that finished. Shows the group's average, and calls out anyone far enough from everyone else. Without a score, shows everyone's ratings. Rating again replaces your score. |
| `predict <guess>` | A sealed prediction about the film: only you see it (`!predict` deletes your message, if the bot has Manage Messages). `np end` posts each one; people react ✅/❌ to judge it (not your own). Called predictions go on the rap sheet. Each prediction is saved against its watch of the film; if the film is swapped before it starts, its predictions go to the watchlist with it. |
| `bingo card` / `bingo mark <n>` / `bingo unmark <n>` | Movie bingo. Everyone gets their own 5×5 card of film tropes for each film (privately; `!bingo` sends it by DM). Mark squares as they happen (autocomplete shows your squares); five in a row across, down or diagonally calls BINGO. Wins go on the rap sheet. |
| `shhh [reason]` | Movie night: a big 🤫 SHHHH telling everyone to be quiet for this bit, naming the film if one's playing, with an optional reason. Pings nobody. |
| `timezone convert [time] [from] [to]` / `timezone set <zone>` / `timezone show [@user]` / `timezone clear` | Convert a time between timezones: `/timezone convert 7pm London New York` → "**19:00** in London (BST) is **14:00** in New York (EDT)", plus the same moment in each reader's own time. Everything's optional but you need a `from` or a `to`: a left-out time is now, and a left-out zone is yours (from `set`), or `BOT_TIMEZONE` if you haven't set one. So `/timezone convert to:Tokyo` is the time in Tokyo now. Zones can be cities, abbreviations (`EST`, `BST`; summer time handled), offsets (`UTC+5:30`) or full names, and autocomplete. `set` saves your timezone once, for every server; `show` gives your time or someone else's (if they've set theirs). Also `!tz`; quote zones with spaces, and use `now` to skip the time: `!tz convert now "New York"`. |
| `abm <measurement>` | Anything But Metric: converts a metric measurement (`3cm`, `20C`, `2.5kg`, `100km/h`, `500ml`, `85dB`…) into an absurd unit. Units live in `ktdi/lib/abm_units.json`. |
| `imperial <measurement>` | The sincere version of `abm`: an accurate conversion to imperial/US units (e.g. `180cm` → 5 ft 10.9 in, `75kg` → 165.3 lb (11 st 11.3 lb), `1l` → US and UK pints). Same inputs as `abm`. |
| `loot` | Declares you're looting the body (posts the perception check GIF). |
| `rapsheet [@user]` | Shows someone's sprays, expunges, bails, Don orders, bribes, committee spending, called predictions and bingo wins (defaults to you). |
| `blame [reason]` | Blames a random person who's spoken recently in the channel. |
| `bribe <amount>` | Only the person last blamed in the channel can use it. Pays to put the blame back on whoever blamed them (who can then bribe it back). Bribe totals go on the rap sheet. |
| `expunge <amount>` | Pay the committee to remove one spray from your own rap sheet. Only works if you have a spray to remove. The payment counts as a bribe (toward your bribe total, the 👑 and the Champion Briber role), and your rap sheet shows how many you've had expunged. |
| `bail <@user> <amount>` | The counterpart to `expunge`: pay to remove one spray from **someone else's** rap sheet (if you think it was unfair). The payment counts as your bribe. Both rap sheets show it: "Bailed out of N sprays by others" and "Bailed others out N times". |
| `committee funds / spend / ledger / propose` | The committee's money. Every `bribe`, `expunge` and `bail` pays in (including ones from before it kept accounts). `funds` (or just `!committee`) shows the balance and recent spending; anyone can `spend <amount> <item>`, but not more than it has, and it goes on the `ledger` and their rap sheet; `propose` suggests something to argue about, and how many the funds would buy. Shared servers share one committee. |
| `linux` | Asks our resident Linux hater a random question about how much he hates Linux. Pings @poltergeis.t by default; set `LINUX_HATER_ID` in `.env` to change who. |
| `anime` | Asks our resident anime watcher (`ANIME_USER_ID` in `.env`) what they think of a random popular anime from [AniList](https://anilist.co), with a random question. Only they are pinged. If AniList is down it picks from a built-in list. |
| `quote add / random / last / show / search / dissociate / claim / delete` | Save and replay things people said. Also: reply to a message with `!quote [@user]` (or `!quote anon`), type `!quote @user what they said -- optional context`, or right-click a message → Apps → **Save quote**. Leaving out the user in `/quote add` (or using `!quote anon`) saves a quote credited to nobody; `dissociate` removes the name (and original-message link) from an existing quote; `claim` lets someone put their own name on an anonymous quote (only ever their own). |
| `campaign add / show / list / edit / remove` | Keep each campaign's D&D Beyond and VTT links under an alias (`Monday game`, anything you like). `show` gives clickable buttons; aliases autocomplete. `!campaign <alias>` shows one. Only whoever added a campaign, or a mod, can edit or remove it. |
| `campaign remind <alias> <when>` / `campaign unremind <alias>` | Scheduled reminders. The time is when the game starts, plus an optional warning: `mondays at 1900, 15 minutes before`, `monday 7pm 1h before`, `every other friday at 7:30pm from 23 oct, half an hour before`. People react 🔔 to the setup message to get pinged; reminders post the campaign's buttons. Times are in `REMINDER_TIMEZONE` (defaults to `BOT_TIMEZONE`, which defaults to UK time). |
| `campaign skip <alias>` / `campaign reschedule <alias> <change>` | For when things change. `skip` skips the next session (fortnightly games shift a week and carry on from there). `reschedule` takes a new warning (`30 minutes before`), `next 26 oct` (the next session's date) or a whole new schedule. All keep everyone's 🔔. |
| `books search <query>` / `books download <ID or title>` | Search a Calibre-Web library and download a book (optional; see below). |
| `settings show` / `settings shared_state <true/false>` / `settings whospray_user [@user]` | Per-server settings, stored in the database. **Shared state** (on by default, needs Manage Server to change) pools quotes, sprays, bribes and campaigns with every other server that has it on; off keeps them local to that server, and switching loses nothing. **whospray_user** chooses the Don, who `/whospray` asks and `/tdoi` obeys (leave it empty to clear); only the user IDs in `WHOSPRAY_ADMIN_IDS` in `.env` can change it, not even server admins. |
| `help [command]` | Lists all commands, grouped by category (Rap sheet, Fun, Movie night, Measurements, Quotes, Campaigns, Utilities), or details for one (e.g. `/help abm` lists every unit it understands). If the list ever outgrows one message it gets ◀ / ▶ page buttons. |

Reacting 💦 to any message also sprays the person who sent it and adds to their rap sheet.

**Optional Champion Briber role:** if a server has a role named `Champion Briber`, the bot gives it to that server's biggest all-time briber after each bribe (and takes it off the previous holder). The bot needs **Manage Roles**, and its own role must sit above `Champion Briber` in the role list. Servers without the role, or where the bot lacks permission, are skipped. Change the name with `BRIBER_ROLE_NAME`.

Spray counts are stored per server in `ktdi.db` (SQLite) next to `bot.py`; set `DB_PATH` to move it.

Text commands need the **Message Content Intent** enabled on the bot's page in the Developer Portal.

## Setup

1. Create an application and bot at https://discord.com/developers/applications and copy the bot token.
2. Invite the bot to your server using the OAuth2 URL generator with the `bot` and `applications.commands` scopes.
3. Create a virtual environment and install the project (Windows):

   ```bash
   py -m venv .venv
   .venv\Scripts\activate
   pip install -e .
   ```

4. Copy `.env.example` to `.env` and set `DISCORD_TOKEN`.
5. Run the bot (with the venv active):

   ```bash
   ktdi
   ```

   or `python bot.py`.

### Library (optional)

`/books` searches a [Calibre-Web](https://github.com/janeczku/calibre-web) server through its OPDS feed and sends books as Discord attachments. To turn it on, set `CALIBRE_URL`, `CALIBRE_USERNAME`, `CALIBRE_PASSWORD` and `BOOKS_GUILD_IDS` in `.env` (see `.env.example`):

- Create a dedicated Calibre-Web user for the bot with only the **download** permission.
- The commands only work, and only appear, in the servers listed in `BOOKS_GUILD_IDS`.
- `/books` replies are only visible to the person who asked; `!books download` sends the file by DM.
- Discord's upload limit (10 MB on unboosted servers) applies. The bot sends the first format in `BOOK_FORMATS` that fits, or says the book is too big.

### Logs

The bot logs startup, every command used, 💦 sprays, bribes and role changes to `logs/ktdi.log` next to `bot.py` (and to the terminal/journal). The file rotates at 1 MB, keeping 5 old files (`ktdi.log.1` … `ktdi.log.5`). To follow it live:

```bash
tail -f logs/ktdi.log
```

### Dev bot

To try changes in a test server before they go live, create a second bot application, invite it to your test server only, fill in `.env.dev` (gitignored; same keys as `.env.example`) and run:

```bash
python bot.py --dev
```

This loads `.env.dev` instead of `.env`. Give the dev bot a different `COMMAND_PREFIX`, only the test server in `GUILD_IDS`, and its own `DB_PATH`.

Slash commands can take a while to appear or update when registered globally. Set `GUILD_IDS` in `.env` to a comma-separated list of server IDs to register them to those servers only, which updates instantly.

## Project layout

For how it all fits together, conventions, and rules for changes, see [ARCHITECTURE.md](ARCHITECTURE.md).

```
bot.py                 # starts the bot (python bot.py [--dev]); also: python -m ktdi, or the ktdi command
ktdi/
├── bot.py             # the bot: startup, loading features, syncing slash commands, command logging
├── config.py          # settings from .env
├── db.py              # database connection, tables, upgrades, and shared state (scope())
├── common.py          # small helpers shared by features
├── features/          # one file per feature, each a discord.py extension with a setup(bot)
│   ├── fun.py         # spray, loot, linux, blame, bribe, rapsheet, 💦, Champion Briber
│   ├── committee.py   # the committee's funds
│   ├── movie.py       # movie night: np, shhh, rate, predict, bingo
│   ├── units.py       # abm, imperial
│   ├── timezones.py   # timezone
│   ├── quotes.py
│   ├── campaigns.py   # campaigns and reminders
│   ├── settings.py
│   ├── books.py
│   └── help.py        # asks each feature for its HELP_CATEGORY and help_extras(), so new features don't touch it
└── lib/               # no Discord code: unit conversions, reminder schedules, Calibre-Web client
tests/                 # pytest
```

To add a feature: create `ktdi/features/<name>.py` with its commands and an `async def setup(bot)` that registers
them, add it to `FEATURES` in `ktdi/features/__init__.py`, set `HELP_CATEGORY` (where it sits on the `/help` list), and
optionally a `help_extras(command)` for `/help <command>`.

## Tests

```bash
pip install -e ".[dev]"
python -m pytest
```

The tests use an in-memory database and fake Discord objects, never your real `.env`, database or token. They cover
every feature, a fake Calibre-Web for `/books` (including that nothing is logged against a reader), and that every
`/help` page fits Discord's limits.
