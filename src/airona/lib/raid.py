from hikari import Snowflakeish
from sqlalchemy import select
from sqlalchemy.orm import Session

from airona.db import model


def create_raid(
    session: Session,
    guild_id: Snowflakeish,
    channel_id: Snowflakeish,
    message_id: Snowflakeish | None,
    host_mention: str,
    when: int,
    title: str | None,
    index: int | None = None,
) -> model.Raid:
    guild = session.get(model.Guild, guild_id) or model.Guild(id=guild_id)
    raid = model.Raid(
        guild_id=guild_id,
        channel_id=channel_id,
        message_id=message_id,
        host_mention=host_mention,
        when=when,
        title=title,
    )
    if index is None:
        guild.raids.append(raid)
    else:
        guild.raids.insert(index, raid)
    session.add(guild)
    session.flush()
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
    session: Session,
    guild_id: Snowflakeish,
    message_id: Snowflakeish,
) -> model.Raid:
    raid = get_raid_by_message_id(session, guild_id, message_id)
    if raid is None:
        raise IndexError(f"Raid not registered.")
    session.delete(raid)
    return raid


def create_raid_user(
    session: Session,
    raid_id: int,
    discord_id: Snowflakeish,
    role: str
) -> model.RaidUser:
    user = model.RaidUser(
        raid_id=raid_id,
        discord_id=discord_id,
        role=role,
        has_cleared=False
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
            (model.RaidUser.raid_id == raid_id) & (model.RaidUser.discord_id == discord_id)
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
