"""One module per feature. Each is a discord.py extension: its setup(bot) registers the feature's commands.

Optional hooks a feature module can define, used by /help:
    HELP_CATEGORY = "🎲 Fun"  (where its commands sit on the main list; a command can override with extras["category"])
    help_extras(command) -> (extra description, [(field name, field text, inline), ...])
    main_help_lines() -> [(category, line), ...]  (main-list lines for things that aren't commands)
"""

# Load order is also the order /help asks features for extra help sections.
FEATURES = [
    "ktdi.features.fun",
    "ktdi.features.committee",
    "ktdi.features.anime",
    "ktdi.features.units",
    "ktdi.features.quotes",
    "ktdi.features.campaigns",
    "ktdi.features.settings",
    "ktdi.features.books",
    "ktdi.features.help",
]
