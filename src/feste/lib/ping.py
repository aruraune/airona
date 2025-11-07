from asyncio import Queue
from datetime import UTC

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.util import undefined
from hikari import Snowflakeish
from sqlalchemy import select
from sqlalchemy.orm import Session

from feste.db import model
from feste.env import cfg

ping_scheduler = AsyncIOScheduler(
    jobstores={"default": SQLAlchemyJobStore(cfg().apscheduler.jobstore)},
    timezone=UTC,
)


def create_ping(
    session: Session,
    guild_id: Snowflakeish,
    role_id: Snowflakeish,
    channel_id: Snowflakeish,
    schedule: str,
    duration: int = 0,
    description: str = "",
    index: int | None = None,
) -> model.Ping:
    try:
        trigger = CronTrigger.from_crontab(schedule)
    except ValueError:
        raise
    if duration < 0:
        raise ValueError("duration must be a non-negative integer")
    guild = session.get(model.Guild, guild_id) or model.Guild(id=guild_id)
    ping = model.Ping(
        role_id=role_id,
        channel_id=channel_id,
        schedule=schedule,
        duration=duration,
        description=description,
    )
    if index is None:
        guild.pings.append(ping)
    else:
        guild.pings.insert(index, ping)
    session.add(guild)
    session.flush()
    optional_args = {}
    if duration != 0:
        optional_args["misfire_grace_time"] = duration
    ping_scheduler.add_job(
        id=f"{ping.id}",
        replace_existing=True,
        trigger=trigger,
        coalesce=True,
        func=put_ping,
        args=(ping.id,),
        **optional_args,
    )
    return ping


def edit_ping(
    session: Session,
    guild_id: Snowflakeish,
    index: int,
    role_id: int | None = None,
    channel_id: int | None = None,
    schedule: str | None = None,
    duration: int | None = None,
    description: str | None = None,
    new_index: int | None = None,
) -> model.Ping:
    guild = session.get(model.Guild, guild_id)
    if guild is None or index >= len(guild.pings):
        raise IndexError(f"No ping at index {index}")
    ping = guild.pings[index]
    if role_id is not None:
        ping.role_id = role_id
    if channel_id is not None:
        ping.channel_id = channel_id
    if schedule is not None:
        try:
            trigger = CronTrigger.from_crontab(schedule)
        except ValueError:
            raise
        ping_scheduler.modify_job(f"{ping.id}", trigger=trigger)
        ping.schedule = schedule
    if duration is not None:
        if duration < 0:
            raise ValueError("duration must be a non-negative integer")
        ping_scheduler.modify_job(
            f"{ping.id}",
            misfire_grace_time=duration if duration != 0 else undefined,
        )
        ping.duration = duration
    if description is not None:
        ping.description = description
    if new_index is not None and new_index != index:
        guild.pings.insert(new_index, guild.pings.pop(index))
        guild.pings.reorder()
    session.add(guild)
    return ping


def delete_ping(
    session: Session,
    guild_id: Snowflakeish,
    index: int,
) -> model.Ping:
    ping = get_ping(session, guild_id, index)
    if ping is None:
        raise IndexError(f"No ping at index {index}")
    ping_scheduler.remove_job(f"{ping.id}")
    session.delete(ping)
    return ping


def get_ping(
    session: Session,
    guild_id: Snowflakeish,
    index: int,
) -> model.Ping | None:
    ping = session.scalar(
        select(model.Ping).where(
            (model.Ping.guild_id == guild_id) & (model.Ping.index == index)
        )
    )
    return ping


ping_queue: Queue[int] = Queue()


def put_ping(ping_id: int) -> None:
    ping_queue.put_nowait(ping_id)
