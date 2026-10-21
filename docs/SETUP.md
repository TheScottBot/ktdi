# Setting up and running

The [README](../README.md) has the quick start. This is the rest: what the bot keeps, the optional extras (the library, RPG rulebooks, the herbal), logs, and running a second bot for testing.

## Where things are kept

Everything the bot remembers (rap sheets, quotes, campaigns, movie nights, the committee's funds…) is in `ktdi.db` (SQLite) next to `bot.py`; set `DB_PATH` to move it. Each row remembers which server it came from, so `/settings shared_state` can pool servers or keep them apart.

Text commands need the **Message Content Intent** enabled on the bot's page in the Developer Portal.

## Library (optional)

`/books` searches a [Calibre-Web](https://github.com/janeczku/calibre-web) server through its OPDS feed and sends books as Discord attachments. To turn it on, set `CALIBRE_URL`, `CALIBRE_USERNAME`, `CALIBRE_PASSWORD` and `BOOKS_GUILD_IDS` in `.env` (see `.env.example`):

- Create a dedicated Calibre-Web user for the bot with only the **download** permission.
- The commands only work, and only appear, in the servers listed in `BOOKS_GUILD_IDS`.
- `/books` replies are only visible to the person who asked; `!books download` sends the file by DM.
- Discord's upload limit (10 MB on unboosted servers) applies. The bot sends the first format in `BOOK_FORMATS` that fits, or says the book is too big.

## RPG rulebooks (optional)

`/rpg` searches a folder of rulebooks in your Dropbox and sends a **private download link** straight from Dropbox (it lasts 4 hours), so big PDFs work: they're usually far over Discord's upload limit. Like `/books`, replies are only visible to the person who asked (`!rpg download` sends the link by DM), and nobody's searches or downloads are logged. To turn it on:

1. Go to https://www.dropbox.com/developers/apps → **Create app** → **Scoped access** → **Full Dropbox** (needed to reach a folder like `Family Room`; the bot only ever reads the folder you give it) → name it, e.g. `KTDI rulebooks`.
2. On the app's **Permissions** tab, tick **files.metadata.read** and **files.content.read** (nothing else) and **Submit**.
3. On the **Settings** tab, copy the **App key** and **App secret**.
4. On your PC, run `python -m ktdi.tools.dropbox_login`, paste the key and secret, open the link it prints, allow the app, and paste back the code. It prints the three `DROPBOX_*` lines for `.env`.
5. In the bot's `.env`, add those, plus the folder as it appears in Dropbox (`https://www.dropbox.com/home/Family%20Room/RPGs` is `/Family Room/RPGs`) and the servers it's for:

   ```
   RPG_DROPBOX_PATH=/Family Room/RPGs
   RPG_GUILD_IDS=111111111111111111
   ```

The commands only work, and only appear, in the servers in `RPG_GUILD_IDS`, and only once every one of these is set. The folder is re-read at most every 10 minutes, so new rulebooks show up within that. The refresh token is like a password for reading your Dropbox: keep `.env` private, and you can revoke it any time under Dropbox → Settings → Connected apps.

## Herbal

`/herbal` posts from `ktdi/lib/herbal.json`, built once from the [1531 *Tacuini sanitatis* on archive.org](https://archive.org/details/bub_gb_9lIU1a_-ddAC). The bad translations are the point, and they come from Google Translate, through Google Sheets (free, no API key):

1. `python -m ktdi.tools.herbal_build extract` reads archive.org's OCR of the book's tables, keeps the cells that look like words (about 550), and writes `herbal-build/herbal_cells.csv` (gitignored), with `GOOGLETRANSLATE` formulas on each row: the translation, then four worse levels for digging.
2. In Google Sheets: **File → Import → Upload** that CSV (**Replace spreadsheet**). Wait until no cell says *Loading…*: it's a few thousand translations, so give it a while (scroll to the bottom right to check), then **File → Download → Comma-separated values**.
3. `python -m ktdi.tools.herbal_build merge` finds that download in your Downloads folder and writes `ktdi/lib/herbal.json`. Commit it, deploy, and `/herbal` is live.

## Almanac plates

`/almanac`'s plant of the day comes with a coloured botanical plate, linked from Wikimedia Commons or the Biodiversity
Heritage Library (nothing to host). Which plate goes with which plant is recorded by hand in
`ktdi/lib/almanac_plates.json`. To look for more, or check the links still work:

```bash
python -m ktdi.tools.almanac_plates_find --plant "Draba verna"
python -m ktdi.tools.almanac_plates_find --bhl --plant "Stapelia rufa"
python -m ktdi.tools.almanac_plates_find --check
```

Candidates and small copies to look at go to `private/almanac/` (gitignored). `--bhl` needs a free BHL API key as
`BHL_API_KEY` in `.env.dev`; the bot itself never uses it.

<a id="allspray"></a>
## Spraying the whole server (/allspray)

`/allspray` needs the bot to see every member of a server, which Discord calls the **Server Members intent**. It's off
unless you turn it on, in this order:

1. In the [Developer Portal](https://discord.com/developers/applications), open the bot's application, go to **Bot**,
   and switch on **Server Members Intent** (under Privileged Gateway Intents). Do it for each bot: the live one and the
   dev one are separate applications.
2. Then add `SERVER_MEMBERS=true` to that bot's `.env` (or `.env.dev`) and restart it.

The order matters: a bot that asks for the intent before it's switched on in the Portal can't log in at all. Without
it, `/allspray` just says it isn't set up.

## Logs

The bot logs startup, every command used (except `/books` and `/rpg`, which are never logged against anyone), 💦 sprays, bribes and role changes to `logs/ktdi.log` next to `bot.py` (and to the terminal/journal). The file rotates at 1 MB, keeping 5 old files (`ktdi.log.1` … `ktdi.log.5`). To follow it live:

```bash
tail -f logs/ktdi.log
```

## Dev bot

To try changes in a test server before they go live, create a second bot application, invite it to your test server only, fill in `.env.dev` (gitignored; same keys as `.env.example`) and run:

```bash
python bot.py --dev
```

This loads `.env.dev` instead of `.env`. Give the dev bot a different `COMMAND_PREFIX`, only the test server in `GUILD_IDS`, and its own `DB_PATH`.

If the log says "Couldn't add slash commands to server …" (Discord's *Missing Access*), that server in `GUILD_IDS` either doesn't have the bot in it, or the bot was invited without the `applications.commands` scope. The bot skips it and starts anyway.

Slash commands can take a while to appear or update when registered globally. Set `GUILD_IDS` in `.env` to a comma-separated list of server IDs to register them to those servers only, which updates instantly.
