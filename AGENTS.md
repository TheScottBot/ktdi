# KTDI: notes for AI coding assistants

Read [ARCHITECTURE.md](ARCHITECTURE.md) before changing code. It covers the structure, data rules, privacy rules and
conventions; this file is only the working rules. (CLAUDE.md imports this file, so this is the one copy.)

- **Never commit or push.** Make and verify changes; the maintainer commits.
- **Run the tests** (`python -m pytest`, ~3 s) before and after changes, and add tests for new behaviour.
- **Keep /help, the README and docs/COMMANDS.md accurate** after every change. `/help` is a short front page, then
  sections, then one page per command (ARCHITECTURE.md §6), and people rely on the command pages for the detail, so
  every new or changed command needs all of:
  - a one-line `description=` (≤ 100 characters: Discord's slash limit), shown in its section's list;
  - its feature's `HELP_CATEGORY` (one of `help.CATEGORIES`), or `extras={"category": ...}` for one command;
  - a **docstring** on the command's function, written for the people using it: what it does beyond the one-liner,
    how to word things, examples, who gets pinged. It's the `/help <command>` page (aliases are added by themselves).
    A group's docstring covers its subcommands; each subcommand keeps its own `description=`;
  - `@app_commands.describe(...)` for each slash option;
  - a row in its section's table in `docs/COMMANDS.md` (the full reference), a one-line entry in the README's
    section index (the short tour), and a line in ARCHITECTURE.md's layout, for a new file.
  Help pages must fit Discord's limits (field ≤ 1024, embed ≤ 6000). `tests/test_registration.py` checks the limits,
  that every command has a section, and that no command's page only repeats its one-liner; add the command to its
  `SLASH_COMMANDS` / `SUBCOMMANDS` lists.
- **Every old book is a source for `/lore`, its shelves and Old Wisdom of the Day.** A new old-book feature (a book,
  dictionary or almanac in 📚 Words & wisdom, 🐉 Beasts & magic or 🌿 Hearth & herbs) isn't finished until:
  - it declares `OLD_BOOK = oldbooks.OldBook(...)` (or a list of them): its `random` entry, for Old Wisdom of the
    Day, and, if it can be searched by topic, `find`, `title`, `link` and `text`, so `/lore` asks it too;
  - it's on a shelf: `shelves=(...)`, one or more of `oldbooks.SHELVES` (nature, folklore, esoteric, words,
    household), so `/nature`, `/esoteric` and the rest ask it. A book that's mostly one shelf with some entries that
    belong on another (/omen's charms against witches are esoteric too) also gives `entry_shelves`;
  - **no slash command of its own**: it's asked through its shelf (`/esoteric book:talisman thing:scarab`), to keep
    Discord's command list short. Its command is a plain `commands.command` (typed-only, `!talisman`, with no
    `app_commands.describe` or autocomplete), and its OldBook gives `names=lambda: DICTIONARY.names` (the shelf's
    autocomplete) and `own_command=False`. Only a book that does something a lookup can't, or that the maintainer
    asks for, gets a slash command too;
  - its shelf says so: the shelf's `about` in `SHELVES` (its `/help` page), `short` too if the book is a big part
    of it, the shelf's row in `docs/COMMANDS.md` and a row for the book under it, and the shelf's line in the
    README's index; and the book in `SHELVED_BOOKS` in `tests/test_registration.py`.
  `tests/test_lore.py` fails without the first two, or if `own_command` doesn't match the command. A new shelf is a
  `SHELVES` entry (the command makes itself; `category` is its /help section), plus its name in
  `tests/test_registration.py`'s `SLASH_COMMANDS`, a row in `docs/COMMANDS.md`, the README's index and the shelves
  listed here; and the books that belong on it.
- **Curating an old book:** keep only what's on an allowlist, and leave out anything with racism or contempt for a
  people or faith (even in passing), mockery of America, sex, gore, cruelty to animals, remedies someone could try,
  misogyny, suicide, harm to children, or anything that takes **gender or sexuality** lightly: people or animals
  changing sex, hermaphrodites, eunuchs, cross-dressing as a joke, "effeminate" and the like as put-downs, mockery
  of gender or sexuality. The bot is LGBTQIA+ safe, however innocently a Victorian author meant an aside. Give every
  reviewer the whole list.
- **Privacy:** never log who used `/books` or `/rpg` or what they searched for or downloaded.
- **Tone:** never mock America, imperial units or Fahrenheit.
- **Don't run the bot with the live token** from `.env`; the homelab is running it. Use `.env.dev` (a separate dev
  bot) or the tests.
- The maintainer deploys by `git pull` + restart on a Linux homelab; `python /opt/ktdi/bot.py` must keep working.
- On the maintainer's Windows machine, `python` may resolve to the Microsoft Store alias; use
  `.venv\Scripts\python.exe`.
