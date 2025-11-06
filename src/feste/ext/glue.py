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
    TextableChannel,
)
from hikari.impl import TextDisplayComponentBuilder
from sqlalchemy import select

from feste.db import model
from feste.db.connection import db
from feste.env import cfg
from feste.ext.settings import settings_group
from feste.typing import Components

plugin = GatewayPlugin(__name__)
scheduler = AsyncIOScheduler(timezone=UTC)


def build_glue() -> Components:
    return [TextDisplayComponentBuilder(content="Not Implemented")]


async def update_all() -> None:
    with db().sm() as session:
        for glue in session.scalars(select(model.Glue)).all():
            try:
                channel = await plugin.client.rest.fetch_channel(glue.channel_id)
            except ForbiddenError, NotFoundError:
                session.delete(glue)
                continue
            if not isinstance(channel, TextableChannel):
                session.delete(glue)
                continue
            last_message = await channel.fetch_history().next()
            if last_message.id == glue.message_id:
                continue
            try:
                await plugin.client.rest.delete_message(
                    glue.channel_id, glue.message_id
                )
            except ForbiddenError, NotFoundError:
                session.delete(glue)
                continue
            try:
                message = await plugin.client.rest.create_message(
                    glue.channel_id, components=build_glue()
                )
            except ForbiddenError:
                session.delete(glue)
                continue
            glue.message_id = message.id
            session.add(glue)
        session.commit()


@plugin.listen()
async def _(_: StartedEvent) -> None:
    scheduler.add_job(update_all, IntervalTrigger(seconds=cfg().glue.interval))
    scheduler.start()


@settings_group.include
@arc.slash_subcommand("glue", "Post a glued reminder menu in this channel.")
async def _(ctx: GatewayContext) -> None:
    with db().sm() as session:
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
                guild.glue.channel_id, components=build_glue()
            )
        except ForbiddenError:
            await ctx.respond("\N{CROSS MARK} Missing `Send Messages` permission.")
            return
        guild.glue.message_id = message.id
        session.add(guild)
        session.commit()
    await ctx.respond("\N{WHITE HEAVY CHECK MARK}", flags=MessageFlag.EPHEMERAL)
