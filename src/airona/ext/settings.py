import arc
from arc import AutodeferMode, GatewayContext, GatewayPlugin
from hikari import MessageFlag, Permissions

from airona.db import model
from airona.db.connection import db
from airona.etc import error_handler

plugin = GatewayPlugin(__name__)

settings_group = plugin.include_slash_group(
    "settings",
    "Manage settings.",
    autodefer=AutodeferMode.EPHEMERAL,
    default_permissions=Permissions.MANAGE_GUILD,
)
settings_group.add_hook(arc.guild_only)
settings_group.set_error_handler(error_handler.guild_only)


@settings_group.include
@arc.slash_subcommand("reset", "Reset all settings to default.")
async def _(ctx: GatewayContext) -> None:
    if ctx.guild_id is None:
        return
    with db().sm.begin() as session:
        guild = session.get(model.Guild, ctx.guild_id)
        if guild is not None:
            session.delete(guild)
    await ctx.respond(
        "\N{WHITE HEAVY CHECK MARK} All settings have been reset to default.",
        flags=MessageFlag.EPHEMERAL,
    )
