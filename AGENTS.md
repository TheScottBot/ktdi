# KTDI: notes for AI coding assistants

Read [ARCHITECTURE.md](ARCHITECTURE.md) before changing code. It covers the structure, data rules, privacy rules and
conventions; this file is only the working rules. (CLAUDE.md imports this file, so this is the one copy.)

- **Never commit or push.** Make and verify changes; the maintainer commits.
- **Run the tests** (`python -m pytest`, ~3 s) before and after changes, and add tests for new behaviour.
- **Keep /help and the README accurate** after every change. `/help` is a short front page, then sections, then one
  page per command (ARCHITECTURE.md §6), and people rely on the command pages for the detail, so every new or changed
  command needs all of:
  - a one-line `description=` (≤ 100 characters: Discord's slash limit), shown in its section's list;
  - its feature's `HELP_CATEGORY` (one of `help.CATEGORIES`), or `extras={"category": ...}` for one command;
  - a **docstring** on the command's function, written for the people using it: what it does beyond the one-liner,
    how to word things, examples, who gets pinged. It's the `/help <command>` page (aliases are added by themselves).
    A group's docstring covers its subcommands; each subcommand keeps its own `description=`;
  - `@app_commands.describe(...)` for each slash option;
  - a row in the README's table for its section (and in ARCHITECTURE.md's layout, for a new file).
  Help pages must fit Discord's limits (field ≤ 1024, embed ≤ 6000). `tests/test_registration.py` checks the limits,
  that every command has a section, and that no command's page only repeats its one-liner; add the command to its
  `SLASH_COMMANDS` / `SUBCOMMANDS` lists.
- **Every old book is a source for `/lore` and Old Wisdom of the Day.** A new old-book feature (a book, dictionary
  or almanac in 📚 Words & wisdom or 🔮 Old oddities) isn't finished until it declares `OLD_BOOK =
  oldbooks.OldBook(...)` (or a list of them): its `random` entry, for Old Wisdom of the Day, and, if it can be
  searched by topic, `find`, `title`, `link` and `text`, so `/lore` asks it too. `tests/test_lore.py` fails without it.
- **Privacy:** never log who used `/books` or `/rpg` or what they searched for or downloaded.
- **Tone:** never mock America, imperial units or Fahrenheit.
- **Don't run the bot with the live token** from `.env`; the homelab is running it. Use `.env.dev` (a separate dev
  bot) or the tests.
- The maintainer deploys by `git pull` + restart on a Linux homelab; `python /opt/ktdi/bot.py` must keep working.
- On the maintainer's Windows machine, `python` may resolve to the Microsoft Store alias; use
  `.venv\Scripts\python.exe`.
