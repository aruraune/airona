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
    MessageActionRowBuilder,
    SectionComponentBuilder,
    TextDisplayComponentBuilder,
)
from sqlalchemy import select

from feste.db import model
from feste.db.connection import db
from feste.lib.ping import get_ping, ping_scheduler
from feste.typing import Components

plugin = GatewayPlugin(__name__)


def menu_custom_id(index: int) -> str:
    return f"subscribe:{index}"


RE_SUBSCRIBE_CUSTOM_ID = re.compile(r"subscribe:(\d+)")


def build_menu(guild_id: Snowflakeish) -> Components:
    components = []
    with db().sm.begin() as session:
        guild = session.get(model.Guild, guild_id)
        if guild is None or not guild.pings:
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
            subscribers_clause = (
                f" ({ping.subscribers})" if ping.subscribers is not None else ""
            )
            components.append(
                SectionComponentBuilder(
                    components=[
                        TextDisplayComponentBuilder(
                            content=f"""\
<@&{ping.role_id}> <t:{beg_timestamp}:R> {ping.description}"""
                        )
                    ],
                    accessory=InteractiveButtonBuilder(
                        custom_id=menu_custom_id(ping.index),
                        label=f"Subscribe{subscribers_clause}",
                        style=ButtonStyle.PRIMARY,
                    ),
                )
            )
        components.append(
            MessageActionRowBuilder(
                components=[
                    InteractiveButtonBuilder(
                        custom_id="subscriptions",
                        emoji="\N{NEWSPAPER}",
                        label="What am I subscribed to?",
                        style=ButtonStyle.SECONDARY,
                    )
                ]
            )
        )
    return components


@plugin.listen()
async def _(event: ComponentInteractionCreateEvent) -> None:
    itx = event.interaction
    if itx.member is None:
        return
    match = RE_SUBSCRIBE_CUSTOM_ID.fullmatch(itx.custom_id)
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


@plugin.listen()
async def _(event: ComponentInteractionCreateEvent) -> None:
    itx = event.interaction
    if itx.custom_id != "subscriptions" or itx.member is None:
        return
    with db().sm.begin() as session:
        pings = session.scalars(
            select(model.Ping).where(model.Ping.guild_id == itx.member.guild_id)
        )
        member_role_ids = frozenset(itx.member.role_ids)
        role_ids = [x.role_id for x in pings if x.role_id in member_role_ids]
    roles_clause = " ".join(f"<@&{x}>" for x in role_ids)
    await itx.create_initial_response(
        ResponseType.MESSAGE_CREATE,
        f"Subscriptions: {roles_clause}" if roles_clause else "*No subscriptions.*",
        flags=MessageFlag.EPHEMERAL,
    )
