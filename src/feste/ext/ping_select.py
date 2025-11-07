import re
from datetime import datetime
from typing import cast

from apscheduler.job import Job
from arc import GatewayPlugin
from hikari import (
    ButtonStyle,
    ComponentInteractionCreateEvent,
    ForbiddenError,
    MessageFlag,
    NotFoundError,
    ResponseType,
    Snowflakeish,
)
from hikari.impl import (
    InteractiveButtonBuilder,
    SectionComponentBuilder,
    TextDisplayComponentBuilder,
)

from feste.db import model
from feste.db.connection import db
from feste.lib.ping import get_ping, ping_scheduler
from feste.typing import Components

plugin = GatewayPlugin(__name__)


def ping_select_custom_id(index: int) -> str:
    return f"ping_select:{index}"


RE_PING_SELECT_CUSTOM_ID = re.compile(r"ping_select:(\d+)")


def build_ping_select(guild_id: Snowflakeish) -> Components:
    components = []
    with db().sm.begin() as session:
        guild = session.get(model.Guild, guild_id)
        if guild is None or len(guild.pings) == 0:
            return [TextDisplayComponentBuilder(content="*No pings.*")]
        components.append(
            TextDisplayComponentBuilder(
                content="## Subscribe to be notified when an event starts!"
            )
        )
        for ping in guild.pings:
            job = cast(Job | None, ping_scheduler.get_job(f"{ping.id}"))
            if job is None:
                continue
            beg_timestamp = int(cast(datetime, job.next_run_time).timestamp())
            components.append(
                SectionComponentBuilder(
                    components=[
                        TextDisplayComponentBuilder(
                            content=f"""\
<@&{ping.role_id}> <t:{beg_timestamp}:R> {ping.description}"""
                        )
                    ],
                    accessory=InteractiveButtonBuilder(
                        custom_id=ping_select_custom_id(ping.index),
                        label="Subscribe",
                        style=ButtonStyle.PRIMARY,
                    ),
                )
            )
    return components


@plugin.listen()
async def _(event: ComponentInteractionCreateEvent) -> None:
    itx = event.interaction
    if itx.member is None:
        return
    match = RE_PING_SELECT_CUSTOM_ID.fullmatch(itx.custom_id)
    if match is None:
        return
    index = int(match.group(1))
    with db().sm.begin() as session:
        ping = get_ping(session, itx.member.guild_id, index)
        if ping is None:
            return
        try:
            if ping.role_id in itx.member.role_ids:
                await itx.member.remove_role(ping.role_id)
                await itx.create_initial_response(
                    ResponseType.MESSAGE_CREATE,
                    f"Removed <@&{ping.role_id}>.",
                    flags=MessageFlag.EPHEMERAL,
                )
            else:
                await itx.member.add_role(ping.role_id)
                await itx.create_initial_response(
                    ResponseType.MESSAGE_CREATE,
                    f"Added <@&{ping.role_id}>.",
                    flags=MessageFlag.EPHEMERAL,
                )
        except NotFoundError:
            await itx.create_initial_response(
                ResponseType.MESSAGE_CREATE, "\N{CROSS MARK} Role not found."
            )
        except ForbiddenError:
            await itx.create_initial_response(
                ResponseType.MESSAGE_CREATE,
                "\N{CROSS MARK} Missing `Manage Roles` permission.",
            )
