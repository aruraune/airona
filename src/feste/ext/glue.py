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
    Snowflakeish,
    StartedEvent,
)
from sqlalchemy.orm import Session

from feste.db import model
from feste.db.connection import db
from feste.env import cfg
from feste.ext.menu import build_menu
from feste.ext.settings import settings_group

plugin = GatewayPlugin(__name__)


@settings_group.include
@arc.slash_subcommand("glue", "Post a glued ping menu in this channel.")
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
                guild.glue.channel_id, components=build_menu(guild.id)
            )
        except ForbiddenError:
            await ctx.respond(
                "\N{CROSS MARK} Missing `Send Messages` permission.",
                flags=MessageFlag.EPHEMERAL,
            )
            return
        guild.glue.message_id = message.id
        session.add(guild)
    await ctx.respond("\N{WHITE HEAVY CHECK MARK}", flags=MessageFlag.EPHEMERAL)


repost_set: set[Snowflakeish] = set()
edit_set: set[Snowflakeish] = set()


def repost_glue_deferred(channel_id: Snowflakeish) -> None:
    repost_set.add(channel_id)


def edit_glue_deferred(channel_id: Snowflakeish) -> None:
    edit_set.add(channel_id)


async def repost_glue(session: Session, glue: model.Glue) -> None:
    try:
        await plugin.client.rest.delete_message(glue.channel_id, glue.message_id)
    except ForbiddenError, NotFoundError:
        session.delete(glue)
        return
    try:
        message = await plugin.client.rest.create_message(
            glue.channel_id, components=build_menu(glue.guild_id)
        )
    except ForbiddenError:
        session.delete(glue)
        return
    glue.message_id = message.id
    session.add(glue)


async def edit_glue(session: Session, glue: model.Glue) -> None:
    try:
        await plugin.client.rest.edit_message(
            glue.channel_id, glue.message_id, components=build_menu(glue.guild_id)
        )
    except ForbiddenError, NotFoundError:
        session.delete(glue)
        return


async def do_deferred() -> None:
    with db().sm.begin() as session:
        async with TaskGroup() as tg:
            global repost_set
            for glue_id in repost_set:
                glue = session.get(model.Glue, glue_id)
                if glue is not None:
                    tg.create_task(repost_glue(session, glue))
            global edit_set
            edit_set -= repost_set
            repost_set = set()
            for glue_id in edit_set:
                glue = session.get(model.Glue, glue_id)
                if glue is not None:
                    tg.create_task(edit_glue(session, glue))
            edit_set = set()


scheduler = AsyncIOScheduler(timezone=UTC)


@plugin.listen()
async def _(_: StartedEvent) -> None:
    scheduler.add_job(do_deferred, IntervalTrigger(seconds=cfg().glue_interval))
    scheduler.start()
