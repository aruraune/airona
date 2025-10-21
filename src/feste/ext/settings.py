import arc
from arc import AutodeferMode, GatewayPlugin
from hikari import Permissions

from feste.etc import error_handler

plugin = GatewayPlugin(__name__)

settings_group = plugin.include_slash_group(
    "settings",
    "Manage settings.",
    autodefer=AutodeferMode.EPHEMERAL,
    default_permissions=Permissions.MANAGE_GUILD,
)
settings_group.add_hook(arc.guild_only)
settings_group.set_error_handler(error_handler.guild_only)
