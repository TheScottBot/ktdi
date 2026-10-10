# KTDI: notes for AI coding assistants

Read [ARCHITECTURE.md](ARCHITECTURE.md) before changing code. It covers the structure, data rules, privacy rules and
conventions; this file is only the working rules. (CLAUDE.md imports this file, so this is the one copy.)

- **Never commit or push.** Make and verify changes; the maintainer commits.
- **Run the tests** (`python -m pytest`, ~3 s) before and after changes, and add tests for new behaviour.
- **Keep /help and the README accurate** after every change. Help pages must fit Discord's limits (field ≤ 1024,
  embed ≤ 6000); `tests/test_registration.py` checks this.
- **Privacy:** never log who used `/books` or `/rpg` or what they searched for or downloaded.
- **Tone:** never mock America, imperial units or Fahrenheit.
- **Don't run the bot with the live token** from `.env`; the homelab is running it. Use `.env.dev` (a separate dev
  bot) or the tests.
- The maintainer deploys by `git pull` + restart on a Linux homelab; `python /opt/ktdi/bot.py` must keep working.
- On the maintainer's Windows machine, `python` may resolve to the Microsoft Store alias; use
  `.venv\Scripts\python.exe`.
