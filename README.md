# ktdi
Keep The Degenerates Inline

A tiny Discord bot for keeping your friends in line. Commands work as slash commands (`/spray`) and as text commands using a configurable prefix (`!spray` by default; set `COMMAND_PREFIX` in `.env`).

| Command | What it does |
|---|---|
| `spray [@user]` | Posts a spray bottle GIF. Target someone to add to their rap sheet. |
| `rapsheet [@user]` | Shows how many times someone has been sprayed (defaults to you). |
| `blame [reason]` | Blames a random person who's spoken recently in the channel. |
| `help` | Lists all commands. |

Reacting 💦 to any message also sprays the person who sent it and adds to their rap sheet.

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

Slash commands can take a few minutes to appear the first time they're synced.
