"""One module per feature. Each is a discord.py extension: its setup(bot) registers the feature's commands.

Optional hooks a feature module can define, used by /help:
    HELP_CATEGORY = "🎲 Fun"  (its /help section, one of help.CATEGORIES; a command can override with extras["category"])
    help_extras(command) -> (extra description, [(field name, field text, inline), ...])
    main_help_lines() -> [(category, line), ...]  (lines in a /help section for things that aren't commands)
"""

# Load order is also the order /help asks features for extra help sections.
FEATURES = [
    "ktdi.features.fun",
    "ktdi.features.futures",
    "ktdi.features.insurance",
    "ktdi.features.wars",
    "ktdi.features.committee",
    "ktdi.features.anime",
    "ktdi.features.herbal",
    "ktdi.features.malleus",
    "ktdi.features.cure",
    "ktdi.features.slang",
    "ktdi.features.deadword",
    "ktdi.features.devils",
    "ktdi.features.dream",
    "ktdi.features.phrase",
    "ktdi.features.beeton",
    "ktdi.features.enquire",
    "ktdi.features.almanac",
    "ktdi.features.melancholy",
    "ktdi.features.pliny",
    "ktdi.features.pseudodoxia",
    "ktdi.features.bestiary",
    "ktdi.features.secrets",
    "ktdi.features.wonder",
    "ktdi.features.goblin",
    "ktdi.features.omen",
    "ktdi.features.flower",
    "ktdi.features.gem",
    "ktdi.features.talisman",
    "ktdi.features.magicsquare",
    "ktdi.features.lore",
    "ktdi.features.wisdom",
    "ktdi.features.etiquette",
    "ktdi.features.movie",
    "ktdi.features.units",
    "ktdi.features.timezones",
    "ktdi.features.weather",
    "ktdi.features.quotes",
    "ktdi.features.campaigns",
    "ktdi.features.settings",
    "ktdi.features.books",
    "ktdi.features.rpg",
    "ktdi.features.help",
]
