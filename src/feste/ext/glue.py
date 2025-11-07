from asyncio import TaskGroup
from datetime import UTC

import arc
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from arc import GatewayContext, GatewayPlugin
from hikari import (
    ForbiddenError,
    MessageFlag,
    NotFoundError,
    StartedEvent,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from feste.db import model
from feste.db.connection import db
from feste.env import cfg
from feste.ext.ping_select import build_ping_select
from feste.ext.settings import settings_group

plugin = GatewayPlugin(__name__)


@settings_group.include
@arc.slash_subcommand("glue", "Post a glued ping selector in this channel.")
async def _(ctx: GatewayContext) -> None:
    with db().sm.begin() as session:
        guild = session.get(model.Guild, ctx.guild_id) or model.Guild(id=ctx.guild_id)
        if guild.glue is None:
            guild.glue = model.Glue()
        else:
            try:
                await plugin.client.rest.delete_message(
                    guild.glue.channel_id, guild.glue.message_id
                )
            except ForbiddenError, NotFoundError:
                pass
        guild.glue.channel_id = ctx.channel_id
        try:
            message = await plugin.client.rest.create_message(
                guild.glue.channel_id, components=build_ping_select(guild.id)
            )
        except ForbiddenError:
            await ctx.respond(
                "\N{CROSS MARK} Missing `Send Messages` permission.",
                flags=MessageFlag.EPHEMERAL,
            )
            return
        guild.glue.message_id = message.id
        guild.glue.queued = False
        session.add(guild)
    await ctx.respond("\N{WHITE HEAVY CHECK MARK}", flags=MessageFlag.EPHEMERAL)


def queue_glue(session: Session, glue: model.Glue) -> None:
    glue.queued = True
    session.add(glue)


async def update_glue(session: Session, glue: model.Glue) -> None:
    if not glue.queued:
        return
    try:
        await plugin.client.rest.delete_message(glue.channel_id, glue.message_id)
    except ForbiddenError, NotFoundError:
        session.delete(glue)
        return
    try:
        message = await plugin.client.rest.create_message(
            glue.channel_id, components=build_ping_select(glue.guild_id)
        )
    except ForbiddenError:
        session.delete(glue)
        return
    glue.message_id = message.id
    glue.queued = False
    session.add(glue)


async def update_all_glue() -> None:
    with db().sm.begin() as session:
        async with TaskGroup() as tg:
            for glue in session.scalars(select(model.Glue)):
                tg.create_task(update_glue(session, glue))


scheduler = AsyncIOScheduler(timezone=UTC)


@plugin.listen()
async def _(_: StartedEvent) -> None:
    scheduler.add_job(update_all_glue, IntervalTrigger(seconds=cfg().glue.interval))
    scheduler.start()
