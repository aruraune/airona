from arc import GatewayContext, GuildOnlyError
from hikari import MessageFlag


async def guild_only(ctx: GatewayContext, e: Exception) -> None:
    if isinstance(e, GuildOnlyError):
        await ctx.respond("\N{CROSS MARK} guild_only", flags=MessageFlag.EPHEMERAL)
        return
    raise e
