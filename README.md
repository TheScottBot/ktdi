# ktdi
Keep The Degenerates Inline

A Discord bot for a group of friends who play D&D together. It keeps everyone in line with a spray bottle and a
permanent record, and keeps them entertained with a shelf of very old books that were confidently wrong about
everything. Commands work as slash commands (`/spray`) and typed (`!spray`; the prefix is `COMMAND_PREFIX` in `.env`).

## Start here

- **`/spray @someone`**: spray the degenerate. It goes on their rap sheet.
- **`/rapsheet`**: see who's been sprayed, and who bribed their way out of it.
- **`/bad`**: a telling-off, in GIF form.
- **`/quote random`**: something someone said, back to haunt them.
- **`/nowplaying`**: movie night, with a countdown so everyone presses play together.

In Discord, `/help` has the same tour: a front page, a page per section, and a page per command with the detail.

## The two halves

**💦 The rap sheet.** Spraying someone puts it on their record. Records can be expunged (for a fee), bail can be paid
for a friend, blame can be passed to whoever spoke last and bribed back again, the committee keeps the money, and
the spray futures market lets you bet on who's next. It's all for show and all remembered.

**📜 The old books.** About two dozen public-domain books, read by hand and kept to what's fun and kind: Pliny's
beasts, Topsell's dragons, a medieval book of magic secrets, turn-of-the-century dreams, superstitions, goblins,
gems and talismans, 1811 slang, Mrs Beeton and two Victorian etiquette manuals. `/lore dragon` asks all of them at once;
`/nature`, `/folklore`, `/esoteric`, `/words` and `/household` ask one shelf; each book has its own command too. Old
Wisdom of the Day posts one in a channel every day, at a time the server picks.

Around those: movie nights, quotes, D&D campaign links and reminders, unit conversions (sincere and absurd),
timezones, the weather, and the library.

## Sections

The same sections as `/help`. Each links to its part of the [full command reference](docs/COMMANDS.md), which has
every subcommand, option and example.

### [💦 Rap sheet](docs/COMMANDS.md#rap-sheet)
Sprays, telling-offs, blame, bribes and the committee.
- `spray`: spray the degenerate · `rapsheet`: someone's sprays, bribes, expunges and bails
- `bad` / `badbonk`: a telling-off GIF, without or with a bonk · `tdoi`: spray yourself, on the Don's orders
- `whospray`: ask the server's chosen sprayer who's next · `blame`: blame someone who's been talking
- `bribe`: pay to put the blame back · `expunge` / `bail`: pay to clear your own or a friend's record
- `committee`: the committee's money · `insurance`: sprays don't count, for a while
- `sprayfutures` / `sprayrate`: bet on who's sprayed next, at today's interest rate

### [🎲 Fun](docs/COMMANDS.md#fun)
Looting, Linux, anime and the war archives.
- `loot`: you're looting the body · `linux` and `anime`: what our resident critics think today
- `wars`: the KTDI War Archives

### [📚 Words & wisdom](docs/COMMANDS.md#words-and-wisdom)
All the old books at once, then dictionaries, idioms, manners and gloom.
- `lore`: what every old book says about something, side by side
- `nature` · `folklore` · `esoteric` · `words` · `household`: the same, on one shelf
- `wisdom`: old wisdom at random, or Old Wisdom of the Day in a channel
- `vulgartongue`: 1811 slang · `deadword`: words English lost · `devils`: Bierce's Devil's Dictionary
- `phrase`: where an idiom comes from · `etiquette`: what a Victorian manual says to do
- `enquire`: the Victorian answer to anything · `melancholy`: Burton's gloomy wisdom (1621)

### [🐉 Beasts & magic](docs/COMMANDS.md#beasts-and-magic)
Monsters, marvels, curiosities, stones, spells, witches and dreams.
- `pliny`: Pliny's Natural History (AD 77) · `pseudodoxia`: Browne's vulgar errors (1646)
- `bestiary`: Topsell's beasts (1607) · `wonder`: Ten Thousand Wonderful Things (c. 1860)
- `secrets`: the Boke of Secretes (1560) · `hammeredofwitches`: witch-finding tips from the Malleus (1486)
- `dream`: what your dream foretells (1901) · `omen`: everyday superstitions (1898)
- `goblin`: Welsh fairies, ghosts and customs (1880) · `gemlore`: precious stones (1913)
- `talisman`: talismans, charms and star signs (1922) · `magicsquare`: Agrippa's planetary squares, and SATOR

### [🌿 Hearth & herbs](docs/COMMANDS.md#hearth-and-herbs)
Mrs Beeton, Culpeper's cures, the language of flowers and the almanac.
- `beeton`: Mrs Beeton's recipes and advice (1861) · `almanac`: today in Hone's Every-Day Book (1826-27)
- `cure` / `plant`: Culpeper's herbal remedies (1653) · `herbal`: a 1531 health handbook, machine-translated
- `flowermeaning`: the Victorian language of flowers (1851)

### [🎬 Movie night](docs/COMMANDS.md#movie-night)
Countdowns, bingo, votes and ratings.
- `nowplaying`: what's on, the countdown, pauses, the watchlist, votes, bingo and ratings · `shhh`: quiet, please

### [📏 Measurements](docs/COMMANDS.md#measurements)
Units, sincerely or absurdly.
- `abm`: Anything But Metric, in something absurd · `imperial`: metric to imperial, sincerely

### [💬 Quotes](docs/COMMANDS.md#quotes)
- `quote`: save and replay the things people say (or right-click a message: **Save quote**)

### [🗓️ Campaigns](docs/COMMANDS.md#campaigns)
- `campaign`: our campaigns' D&D Beyond and VTT links, and session reminders

### [🔧 Utilities](docs/COMMANDS.md#utilities)
Timezones, weather and settings.
- `timezone`: convert times between timezones · `weather`: the forecast, and what old folk wisdom makes of it
- `books`: the library (optional) · `rpg`: RPG rulebooks (optional)
- `settings`: this server's settings · `help`: the tour, in Discord

## Running it

1. Create an application and bot at https://discord.com/developers/applications, copy the token, and turn on the
   **Message Content Intent** (for typed commands).
2. Invite it with the OAuth2 URL generator, scopes `bot` and `applications.commands`.
3. Install it (Windows shown; on Linux, `python3 -m venv .venv` and `source .venv/bin/activate`):

   ```bash
   py -m venv .venv
   .venv\Scripts\activate
   pip install -e .
   ```

4. Copy `.env.example` to `.env` and set `DISCORD_TOKEN`.
5. Run `ktdi` (or `python bot.py`).

[docs/SETUP.md](docs/SETUP.md) has the rest: where everything is kept, the optional library, RPG rulebooks and herbal,
logs, and a second bot for testing.

## Changing it

[ARCHITECTURE.md](ARCHITECTURE.md) is how it fits together and the rules for changes (adding a feature, adding an
old book); [AGENTS.md](AGENTS.md) is the short list of working rules. Run the tests before and after:

```bash
pip install -e ".[dev]"
python -m pytest
```

They use an in-memory database and fake Discord objects, never your real `.env`, database or token.
