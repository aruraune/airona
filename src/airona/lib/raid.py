from asyncio import Queue
from datetime import UTC, datetime

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from hikari import Snowflakeish
from sqlalchemy import select
from sqlalchemy.orm import Session

from airona.db import model
from airona.env import raid_cfg


def create_raid(
    raid_scheduler: AsyncIOScheduler,
    session: Session,
    guild_id: Snowflakeish,
    channel_id: Snowflakeish,
    message_id: Snowflakeish | None,
    host_discord_id: Snowflakeish,
    host_username: str,
    host_uid: str,
    when: int,
    title: str | None,
) -> model.Raid:
    try:
        dt = datetime.fromtimestamp(when, tz=UTC)
        trigger = DateTrigger(run_date=dt)
    except ValueError:
        raise
    guild = session.get(model.Guild, guild_id) or model.Guild(id=guild_id)
    raid = model.Raid(
        guild_id=guild_id,
        channel_id=channel_id,
        message_id=message_id,
        host_discord_id=host_discord_id,
        host_username=host_username,
        host_uid=host_uid,
        when=when,
        title=title,
    )
    guild.raids.append(raid)
    session.add(guild)
    session.flush()
    raid_scheduler.add_job(
        id=f"{raid.id}",
        replace_existing=True,
        trigger=trigger,
        coalesce=True,
        misfire_grace_time=raid_cfg().raid_misfire_grace_time,
        func=put_raid,
        args=(raid.id,),
    )
    return raid


def get_raid_by_raid_id(
    session: Session,
    raid_id: int,
) -> model.Raid | None:
    raid = session.scalar(select(model.Raid).where(model.Raid.id == raid_id))
    return raid


def get_raid_by_message_id(
    session: Session,
    guild_id: Snowflakeish,
    message_id: Snowflakeish,
) -> model.Raid | None:
    raid = session.scalar(
        select(model.Raid).where(
            (model.Raid.guild_id == guild_id) & (model.Raid.message_id == message_id)
        )
    )
    return raid


def get_all_raids(session: Session) -> list[model.Raid]:
    return list(session.scalars(select(model.Raid)))


def delete_raid_by_message_id(
    raid_scheduler: AsyncIOScheduler,
    session: Session,
    guild_id: Snowflakeish,
    message_id: Snowflakeish,
) -> model.Raid:
    raid = get_raid_by_message_id(session, guild_id, message_id)
    if raid is None:
        raise IndexError("Raid not registered.")
    try:
        raid_scheduler.remove_job(f"{raid.id}")
    except JobLookupError:
        pass
    session.delete(raid)
    return raid


def create_raid_user(
    session: Session,
    raid_id: int,
    discord_id: Snowflakeish,
    role: str,
    has_cleared: bool | None = None,
) -> model.RaidUser:
    user = model.RaidUser(
        raid_id=raid_id, discord_id=discord_id, role=role, has_cleared=has_cleared
    )
    session.add(user)
    session.flush()
    return user


def get_raid_user_by_discord_id(
    session: Session,
    raid_id: int,
    discord_id: Snowflakeish,
) -> model.RaidUser | None:
    user = session.scalar(
        select(model.RaidUser).where(
            (model.RaidUser.raid_id == raid_id)
            & (model.RaidUser.discord_id == discord_id)
        )
    )
    return user


def edit_raid_user(
    session: Session,
    raid_id: int,
    discord_id: Snowflakeish,
    role: str | None = None,
    has_cleared: bool | None = None,
) -> model.RaidUser:
    user = get_raid_user_by_discord_id(session, raid_id, discord_id)
    if user is None:
        raise IndexError(f"User not registered for raid {raid_id}")
    if role is not None:
        user.role = role
    if has_cleared is not None:
        user.has_cleared = has_cleared
    session.add(user)
    return user


def delete_raid_user_by_discord_id(
    session: Session,
    raid_id: int,
    discord_id: Snowflakeish,
) -> model.RaidUser:
    user = get_raid_user_by_discord_id(session, raid_id, discord_id)
    if user is None:
        raise IndexError(f"User not registered for raid {raid_id}")
    session.delete(user)
    return user


raid_queue: Queue[int] = Queue()


def put_raid(raid_id: int) -> None:
    raid_queue.put_nowait(raid_id)
