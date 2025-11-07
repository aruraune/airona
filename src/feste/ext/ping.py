import arc
from arc import (
    ChannelParams,
    GatewayContext,
    GatewayPlugin,
    IntParams,
    Option,
    RoleParams,
    StrParams,
)
from hikari import (
    ForbiddenError,
    InternalServerError,
    MessageFlag,
    NotFoundError,
    Role,
    Snowflakeish,
    StartedEvent,
    TextableChannel,
)
from hikari.impl import TextDisplayComponentBuilder

from feste.db import model
from feste.db.connection import db
from feste.ext.glue import queue_glue
from feste.ext.settings import settings_group
from feste.lib.ping import (
    create_ping,
    delete_ping,
    edit_ping,
    ping_queue,
    ping_scheduler,
)
from feste.typing import Components

plugin = GatewayPlugin(__name__)

ping_group = settings_group.include_subgroup("ping", "Manage pings.")
MAX_PINGS = 12


@ping_group.include
@arc.slash_subcommand("create", "Create a new ping.")
async def _(
    ctx: GatewayContext,
    role: Option[Role, RoleParams("the role to ping.")],
    schedule: Option[str, StrParams("the schedule as a cron expression.")],
    duration: Option[
        int,
        IntParams(
            "the duration (in seconds) of the event referenced by the ping.", min=0
        ),
    ] = 0,
    channel: Option[
        TextableChannel | None, ChannelParams("the channel to post the ping in.")
    ] = None,
    description: Option[str, StrParams("describes the ping.")] = "",
    index: Option[int | None, IntParams("the index to insert the ping at.")] = None,
) -> None:
    if ctx.guild_id is None:
        return
    try:
        with db().sm.begin() as session:
            guild = session.get(model.Guild, ctx.guild_id)
            if guild is not None and len(guild.pings) >= MAX_PINGS:
                await ctx.respond(
                    f"\N{CROSS MARK} Maximum of {MAX_PINGS} pings allowed.",
                    flags=MessageFlag.EPHEMERAL,
                )
                return
            create_ping(
                session,
                ctx.guild_id,
                role.id,
                channel.id if channel else ctx.channel_id,
                schedule,
                duration,
                description,
                index,
            ).id
    except ValueError as e:
        await ctx.respond(f"\N{CROSS MARK} {e}", flags=MessageFlag.EPHEMERAL)
        return
    await ctx.respond(
        components=build_ping_list(ctx.guild_id),
        flags=MessageFlag.EPHEMERAL,
    )


@ping_group.include
@arc.slash_subcommand("edit", "Modify an existing ping.")
async def _(
    ctx: GatewayContext,
    index: Option[int, IntParams("the index of the ping to modify.")],
    role: Option[Role | None, RoleParams("the role to ping.")] = None,
    channel: Option[
        TextableChannel | None, ChannelParams("the channel to post the ping in.")
    ] = None,
    schedule: Option[
        str | None, StrParams("the schedule as a cron expression.")
    ] = None,
    duration: Option[
        int | None,
        IntParams(
            "the duration (in seconds) of the event referenced by the ping.", min=0
        ),
    ] = None,
    description: Option[str | None, StrParams("describes the ping.")] = None,
    new_index: Option[int | None, IntParams("the index to move the ping to.")] = None,
) -> None:
    if ctx.guild_id is None:
        return
    try:
        with db().sm.begin() as session:
            edit_ping(
                session,
                ctx.guild_id,
                index,
                role.id if role is not None else None,
                channel.id if channel is not None else None,
                schedule,
                duration,
                description,
                new_index,
            ).index
    except ValueError as e:
        await ctx.respond(f"\N{CROSS MARK} {e}", flags=MessageFlag.EPHEMERAL)
        return
    await ctx.respond(
        components=build_ping_list(ctx.guild_id),
        flags=MessageFlag.EPHEMERAL,
    )


@ping_group.include
@arc.slash_subcommand("delete", "Delete an existing ping.")
async def _(
    ctx: GatewayContext,
    index: Option[int, IntParams("the index of the ping to delete.")],
) -> None:
    if ctx.guild_id is None:
        return
    try:
        with db().sm.begin() as session:
            delete_ping(session, ctx.guild_id, index)
    except IndexError as e:
        await ctx.respond(f"\N{CROSS MARK} {e}", flags=MessageFlag.EPHEMERAL)
        return
    await ctx.respond(
        components=build_ping_list(ctx.guild_id),
        flags=MessageFlag.EPHEMERAL,
    )


@ping_group.include
@arc.slash_subcommand("list", "List all existing pings.")
async def _(
    ctx: GatewayContext,
) -> None:
    if ctx.guild_id is None:
        return
    await ctx.respond(
        components=build_ping_list(ctx.guild_id),
        flags=MessageFlag.EPHEMERAL,
    )


def build_ping_list(guild_id: Snowflakeish) -> Components:
    components = []
    with db().sm.begin() as session:
        guild = session.get(model.Guild, guild_id)
        if guild is None or len(guild.pings) == 0:
            return [TextDisplayComponentBuilder(content="*No pings.*")]
        for ping in guild.pings:
            components.append(
                TextDisplayComponentBuilder(
                    content=f"""\
`{ping.index}` <@&{ping.role_id}> <#{ping.channel_id}> @ `{ping.schedule}` ({ping.duration}s) {ping.description}"""
                )
            )
    return components


async def post_ping(ping_id: int) -> None:
    with db().sm.begin() as session:
        ping = session.get(model.Ping, ping_id)
        if ping is None:
            return
        try:
            await plugin.client.rest.create_message(
                ping.channel_id,
                f"<@&{ping.role_id}> {ping.description}",
                role_mentions=[ping.role_id],
            )
        except ForbiddenError, NotFoundError:
            session.delete(ping)
            return
        except InternalServerError:
            return
        glue = session.get(model.Glue, ping.channel_id)
        if glue is None:
            return
        queue_glue(session, glue)


async def post_ping_loop() -> None:
    while True:
        ping_id = await ping_queue.get()
        plugin.client.create_task(post_ping(ping_id))


@plugin.listen()
async def _(_: StartedEvent) -> None:
    ping_scheduler.start()
    plugin.client.create_task(post_ping_loop())
