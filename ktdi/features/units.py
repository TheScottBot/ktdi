"""/abm (Anything But Metric) and /imperial."""

from discord.ext import commands

from ktdi.lib import abm


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


def help_extras(command: commands.Command) -> tuple[str, list[tuple[str, str, bool]]]:
    if command.name not in ("abm", "imperial"):
        return "", []
    description = ("\n\nType a number and a metric unit, with or without a space: `3cm`, `2.5 kg`, `100 km/h`. "
                   "Spelled-out names like `metres` or `litres` work too. Capitals mostly don't matter, "
                   "except `mW` vs `MW`.")
    return description, [(dimension, units, True) for dimension, units in abm.input_unit_help()]


async def setup(bot: commands.Bot):
    bot.add_command(abm_command)
    bot.add_command(imperial_command)
