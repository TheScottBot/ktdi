# ktdi
Keep The Degenerates Inline

A tiny Discord bot for keeping your friends in line. Commands work as slash commands (`/spray`) and as text commands using a configurable prefix (`!spray` by default; set `COMMAND_PREFIX` in `.env`).

| Command | What it does |
|---|---|
| `spray [@user]` | Posts a spray bottle GIF. Target someone to add to their rap sheet. |
| `abm <measurement>` | Anything But Metric: converts a metric measurement (`3cm`, `20C`, `2.5kg`, `100km/h`, `500ml`, `85dB`…) into an absurd unit. Units live in `abm_units.json`. |
| `imperial <measurement>` | The sincere version of `abm`: an accurate conversion to imperial/US units (e.g. `180cm` → 5 ft 10.9 in, `75kg` → 165.3 lb (11 st 11.3 lb), `1l` → US and UK pints). Same inputs as `abm`. |
| `loot` | Declares you're looting the body (posts the perception check GIF). |
| `rapsheet [@user]` | Shows someone's sprays and bribes (defaults to you). |
| `blame [reason]` | Blames a random person who's spoken recently in the channel. |
| `bribe <amount>` | Only the person last blamed in the channel can use it. Pays to put the blame back on whoever blamed them (who can then bribe it back). Bribe totals go on the rap sheet. |
| `linux` | Asks our resident Linux hater a random question about how much he hates Linux. Pings our Linux hater by default; set `LINUX_HATER_ID` in `.env` to change who. |
| `quote add / random / last / show / search / dissociate / claim / delete` | Save and replay things people said. Also: reply to a message with `!quote [@user]` (or `!quote anon`), type `!quote @user what they said -- optional context`, or right-click a message → Apps → **Save quote**. Leaving out the user in `/quote add` (or using `!quote anon`) saves a quote credited to nobody; `dissociate` removes the name (and original-message link) from an existing quote; `claim` lets someone put their own name on an anonymous quote (only ever their own). |
| `campaign add / show / list / edit / remove` | Keep each campaign's D&D Beyond and VTT links under an alias (`Monday game`, anything you like). `show` gives clickable buttons; aliases autocomplete. `!campaign <alias>` shows one. Only whoever added a campaign, or a mod, can edit or remove it. |
| `campaign remind <alias> <when>` / `campaign unremind <alias>` | Scheduled reminders. The time is when the game starts, plus an optional warning: `mondays at 1900, 15 minutes before`, `monday 7pm 1h before`, `every other friday at 7:30pm from 23 oct, half an hour before`. People react 🔔 to the setup message to get pinged; reminders post the campaign's buttons. Times are in `REMINDER_TIMEZONE` (default UK time). |
| `campaign skip <alias>` / `campaign reschedule <alias> <change>` | For when things change. `skip` skips the next session (fortnightly games shift a week and carry on from there). `reschedule` takes a new warning (`30 minutes before`), `next 26 oct` (the next session's date) or a whole new schedule. All keep everyone's 🔔. |
| `books search <query>` / `books download <ID or title>` | Search a Calibre-Web library and download a book (optional; see below). |
| `help [command]` | Lists all commands, or details for one (e.g. `/help abm` lists every unit it understands). |

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
