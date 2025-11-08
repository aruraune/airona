from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from arc import GatewayPlugin
from hikari import MemberUpdateEvent, StartedEvent
from sqlalchemy import select

from feste.db import model
from feste.db.connection import db
from feste.env import cfg
from feste.ext.glue import edit_glue_deferred

plugin = GatewayPlugin(__name__)

scheduler = AsyncIOScheduler(timezone=UTC)


async def update_subscribers() -> None:
    with db().sm.begin() as session:
        for ping in session.scalars(select(model.Ping)):
            members = plugin.client.cache.get_members_view_for_guild(
                ping.guild_id
            ).values()
            if len(members) == 0:
                continue
            subscribers = sum(1 for x in members if ping.role_id in x.role_ids)
            if ping.subscribers == subscribers:
                continue
            ping.subscribers = subscribers
            session.add(ping)
            edit_glue_deferred(ping.channel_id)


@plugin.listen()
async def _(event: MemberUpdateEvent) -> None:
    if event.old_member is None or event.old_member.role_ids == event.member.role_ids:
        return
    with db().sm.begin() as session:
        for ping in session.scalars(select(model.Ping)):
            if ping.subscribers is None:
                continue
            was_subscribed = ping.role_id in event.old_member.role_ids
            is_subscribed = ping.role_id in event.member.role_ids
            if was_subscribed == is_subscribed:
                continue
            ping.subscribers += 1 if is_subscribed else -1
            session.add(ping)
            edit_glue_deferred(ping.channel_id)


@plugin.listen()
async def _(_: StartedEvent) -> None:
    scheduler.add_job(
        update_subscribers,
        IntervalTrigger(seconds=cfg().subscribers_interval),
        next_run_time=datetime.now() + timedelta(seconds=15),
    )
    scheduler.start()
