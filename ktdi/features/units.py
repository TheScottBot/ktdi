"""/abm (Anything But Metric), /imperial and /metric (the other way round)."""

from discord import app_commands
from discord.ext import commands

from ktdi.lib import abm

HELP_CATEGORY = "📏 Measurements"


@commands.hybrid_command(name="abm", description="Anything But Metric: convert a measurement into something absurd.")
async def abm_command(ctx: commands.Context, *, measurement: str):
    try:
        await ctx.send(abm.convert(measurement))
    except abm.ABMError as error:
        await ctx.send(str(error), ephemeral=True)


@commands.hybrid_command(name="imperial", description="Sincerely convert a metric measurement to imperial/US units.")
async def imperial_command(ctx: commands.Context, *, measurement: str):
    try:
        await ctx.send(abm.to_imperial(measurement))
    except abm.ABMError as error:
        await ctx.send(str(error), ephemeral=True)


@commands.hybrid_command(name="metric",
                         description="Sincerely convert an imperial/US measurement to metric (5ft 10, 1 pint, 70F).")
@app_commands.describe(measurement="A number and an imperial or US unit: 5ft 10, 5'10\", 11st 4lb, 2 cups, 70F, 60 mph")
async def metric_command(ctx: commands.Context, *, measurement: str):
    """The other way round from `/imperial`: an accurate conversion from imperial or US units to metric. Heights and
    weights can be in two parts (`5ft 10`, `5'10"`, `11st 4lb`, `2 lb 3 oz`). A unit that's different in the UK and
    the US (a pint, a quart, a gallon, a fluid ounce, a ton) gets both, unless you say which (`1 US pint`, `1 UK
    gallon`); teaspoons, tablespoons and cups are American. Give it something already metric and it says so, with
    the imperial."""
    try:
        await ctx.send(abm.to_metric(measurement))
    except abm.ABMError as error:
        await ctx.send(str(error), ephemeral=True)


def help_extras(command: commands.Command) -> tuple[str, list[tuple[str, str, bool]]]:
    if command.name == "metric":
        return "", [(dimension, units, True) for dimension, units in abm.metric_unit_help()]
    if command.name not in ("abm", "imperial"):
        return "", []
    description = ("\n\nType a number and a metric unit, with or without a space: `3cm`, `2.5 kg`, `100 km/h`. "
                   "Spelled-out names like `metres` or `litres` work too. Capitals mostly don't matter, "
                   "except `mW` vs `MW`.")
    return description, [(dimension, units, True) for dimension, units in abm.input_unit_help()]


async def setup(bot: commands.Bot):
    bot.add_command(abm_command)
    bot.add_command(imperial_command)
    bot.add_command(metric_command)
