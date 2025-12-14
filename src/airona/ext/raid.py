from datetime import UTC, datetime

import arc
import hikari
from apscheduler.jobstores.base import JobLookupError
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from arc import (
    AutodeferMode,
    BoolParams,
    GatewayContext,
    GatewayPlugin,
    IntParams,
    Option,
    StrParams,
    UserParams,
)
from hikari import (
    ButtonStyle,
    ComponentInteractionCreateEvent,
    Emoji,
    ForbiddenError,
    InternalServerError,
    MessageFlag,
    NotFoundError,
    Permissions,
    ResponseType,
    Snowflakeish,
    StartedEvent,
)
from hikari.impl import (
    InteractiveButtonBuilder,
    MessageActionRowBuilder,
    TextDisplayComponentBuilder,
)

from airona.db import model
from airona.db.connection import db
from airona.env import cfg, raid_cfg
from airona.lib.raid import (
    create_raid,
    create_raid_user,
    delete_raid_by_message_id,
    delete_raid_user_by_discord_id,
    edit_raid_user,
    get_all_raids,
    get_raid_by_message_id,
    get_raid_by_raid_id,
    get_raid_user_by_discord_id,
    raid_queue,
)
from airona.typing import Components

plugin = GatewayPlugin(__name__)

raid_group = plugin.include_slash_group(
    "raid",
    "Manage raids.",
    autodefer=AutodeferMode.EPHEMERAL,
    default_permissions=Permissions.CREATE_EVENTS | Permissions.MANAGE_EVENTS,
)

USER_ROLE_DPS = "dps"
USER_ROLE_TANK = "tank"
USER_ROLE_SUPPORT = "support"

RAID_PREFIX = "raid"
RAID_ROLE_PREFIX = f"{RAID_PREFIX}:role"
RAID_ROLE_DPS = f"{RAID_ROLE_PREFIX}:{USER_ROLE_DPS}"
RAID_ROLE_TANK = f"{RAID_ROLE_PREFIX}:{USER_ROLE_TANK}"
RAID_ROLE_SUPPORT = f"{RAID_ROLE_PREFIX}:{USER_ROLE_SUPPORT}"
RAID_CLEARED = f"{RAID_PREFIX}:cleared"
RAID_SIGNOFF = f"{RAID_PREFIX}:signoff"


raid_scheduler = AsyncIOScheduler(
    jobstores={
        "default": SQLAlchemyJobStore(cfg().apscheduler.jobstore),
        "memory": MemoryJobStore(),
    },
    timezone=UTC,
)


@raid_group.include
@arc.slash_subcommand("create", "Create a new raid.")
async def _(
    ctx: GatewayContext,
    host: Option[hikari.User, UserParams("the host of the raid.")],
    ingame_host_username: Option[str, StrParams("the in-game username of the host.")],
    ingame_host_uid: Option[str, StrParams("the in-game uid of the host.")],
    when: Option[
        int,
        IntParams(
            "the time when the raid will start (timestamp in seconds, use hammertime.cyou)."
        ),
    ],
    title: Option[
        str, StrParams("the title of the raid announcement (e.g. All raids, Light NM).")
    ],
) -> None:
    if ctx.guild_id is None:
        return
    if when <= int(datetime.now(UTC).timestamp()):
        await ctx.respond(
            "\N{CROSS MARK} The raid time must be in the future.",
            flags=MessageFlag.EPHEMERAL,
        )
        return
    try:
        try:
            message = await plugin.client.rest.create_message(
                ctx.channel_id,
                components=build_raid_message(
                    when,
                    title,
                    host.id,
                    host_name=ingame_host_username,
                    host_uid=ingame_host_uid,
                    guild_id=ctx.guild_id,
                    channel_id=ctx.channel_id,
                ),
                user_mentions=[host.id],
            )
            await plugin.client.rest.edit_message(
                ctx.channel_id,
                message.id,
                components=build_raid_message(
                    when,
                    title,
                    host.id,
                    host_name=ingame_host_username,
                    host_uid=ingame_host_uid,
                    guild_id=ctx.guild_id,
                    channel_id=ctx.channel_id,
                    message_id=message.id,
                ),
                user_mentions=[host.id],
            )
            thread = await plugin.client.rest.create_message_thread(
                ctx.channel_id,
                message.id,
                f"{title} @ {datetime.fromtimestamp(when, UTC).strftime('%Y-%m-%d %H:%M')} UTC",
            )
            await plugin.client.rest.create_message(
                thread.id,
                components=build_initial_thread_message(
                    ctx.guild_id,
                    ctx.channel_id,
                    message.id,
                ),
            )
        except ForbiddenError:
            await ctx.respond(
                "\N{CROSS MARK} Missing `Send Messages` permission.",
                flags=MessageFlag.EPHEMERAL,
            )
            return
        with db().sm.begin() as session:
            try:
                create_raid(
                    raid_scheduler,
                    session,
                    ctx.guild_id,
                    ctx.channel_id,
                    message.id,
                    host.id,
                    ingame_host_username,
                    ingame_host_uid,
                    when,
                    title,
                )
            except:
                await plugin.client.rest.delete_message(ctx.channel_id, message.id)
                raise
    except ValueError as e:
        await ctx.respond(f"\N{CROSS MARK} {e}", flags=MessageFlag.EPHEMERAL)
        return
    await ctx.respond(
        content="\N{WHITE HEAVY CHECK MARK}",
        flags=MessageFlag.EPHEMERAL,
    )


@raid_group.include
@arc.slash_subcommand("add", "Add a user to a raid.")
async def _(
    ctx: GatewayContext,
    message_id: Option[str, StrParams("the id of the raid.")],
    user: Option[hikari.User, UserParams("the user to add.")],
    role: Option[
        str,
        StrParams(
            "the role of the user (dps, tank, support).",
            choices=[USER_ROLE_DPS, USER_ROLE_TANK, USER_ROLE_SUPPORT],
        ),
    ],
    has_cleared: Option[
        bool, BoolParams("whether the user has already cleared the raid.")
    ],
) -> None:
    if ctx.guild_id is None:
        return
    try:
        message_id: int = int(message_id)
    except ValueError:
        await ctx.respond(
            "\N{CROSS MARK} Invalid `message_id`.", flags=MessageFlag.EPHEMERAL
        )
        return
    if role not in [USER_ROLE_DPS, USER_ROLE_TANK, USER_ROLE_SUPPORT]:
        await ctx.respond(
            "\N{CROSS MARK} Invalid role.",
            flags=MessageFlag.EPHEMERAL,
        )
        return
    try:
        with db().sm.begin() as session:
            raid = get_raid_by_message_id(session, ctx.guild_id, message_id)
            raid_id = None

            if raid is not None:
                raid_id = raid.id

                raid_user = get_raid_user_by_discord_id(session, raid.id, user.id)

                if raid_user is not None:
                    edit_raid_user(
                        session, raid.id, user.id, role=role, has_cleared=has_cleared
                    )
                else:
                    create_raid_user(
                        session, raid.id, user.id, role=role, has_cleared=has_cleared
                    )

        if raid_id is not None:
            await update_raid_message(raid_id)
        else:
            await ctx.respond(
                "\N{CROSS MARK} Raid does not exist.",
                flags=MessageFlag.EPHEMERAL,
            )
    except ValueError as e:
        await ctx.respond(f"\N{CROSS MARK} {e}", flags=MessageFlag.EPHEMERAL)
        return
    await ctx.respond(
        content="\N{WHITE HEAVY CHECK MARK}",
        flags=MessageFlag.EPHEMERAL,
    )


@raid_group.include
@arc.slash_subcommand("remove", "Remove a user from a raid.")
async def _(
    ctx: GatewayContext,
    message_id: Option[str, StrParams("the id of the raid.")],
    user: Option[hikari.User, UserParams("the user to add.")],
    reason: Option[str, StrParams("tell the user why you are removing them.")],
) -> None:
    if ctx.guild_id is None:
        return
    try:
        message_id: int = int(message_id)
    except ValueError:
        await ctx.respond(
            "\N{CROSS MARK} Invalid `message_id`.", flags=MessageFlag.EPHEMERAL
        )
        return
    try:
        raid_user_remove_response = None

        with db().sm.begin() as session:
            raid = get_raid_by_message_id(session, ctx.guild_id, message_id)
            raid_id = None

            if raid is not None:
                raid_id = raid.id
                raid_user = get_raid_user_by_discord_id(session, raid.id, user.id)

                if raid_user is None:
                    await ctx.respond(
                        "\N{CROSS MARK} User is not part of this raid.",
                        flags=MessageFlag.EPHEMERAL,
                    )
                    return

                delete_raid_user_by_discord_id(session, raid.id, user.id)

                raid_user_remove_response = build_raid_removal_message(
                    raid.guild_id,
                    raid.channel_id,
                    raid.message_id,
                    reason,
                    raid.when,
                    raid.title,
                    raid.id,
                    raid.users,
                    raid.host_username,
                    raid.host_uid,
                )

        if raid_user_remove_response is None:
            await ctx.respond(
                "\N{CROSS MARK} Raid does not exist.",
                flags=MessageFlag.EPHEMERAL,
            )
            return

        if raid_id is not None:
            await update_raid_message(raid_id)

        try:
            dm_channel = await plugin.client.rest.create_dm_channel(user.id)

            await plugin.client.rest.create_message(
                dm_channel.id,
                components=raid_user_remove_response,
            )
        except Exception as e:
            print(f"Failed to send DM to {user.id}: {e}")
            pass
    except ValueError as e:
        await ctx.respond(f"\N{CROSS MARK} {e}", flags=MessageFlag.EPHEMERAL)
        return
    await ctx.respond(
        content="\N{WHITE HEAVY CHECK MARK}",
        flags=MessageFlag.EPHEMERAL,
    )


async def update_raid_message(
    raid_id: int,
):
    with db().sm.begin() as session:
        raid = get_raid_by_raid_id(session, raid_id)

        if raid is None:
            return

        channel_id = raid.channel_id
        message_id = raid.message_id
        raid_message = build_raid_message(
            raid.when,
            raid.title,
            raid.host_discord_id,
            raid.users,
            raid.host_username,
            raid.host_uid,
            raid.guild_id,
            raid.channel_id,
            raid.message_id,
        )
        user_mentions = [raid.host_discord_id] + [
            user.discord_id for user in raid.users
        ]

    try:
        await plugin.client.rest.edit_message(
            channel_id, message_id, components=raid_message, user_mentions=user_mentions
        )
    except NotFoundError:
        with db().sm.begin() as session:
            delete_raid_by_message_id(
                raid_scheduler, session, raid.guild_id, raid.message_id
            )
        return


def build_raid_message(
    when: int,
    title: str,
    host_discord_id: int,
    users: list[model.RaidUser] | None = None,
    host_name: str | None = None,
    host_uid: str | None = None,
    guild_id: Snowflakeish | None = None,
    channel_id: Snowflakeish | None = None,
    message_id: Snowflakeish | None = None,
) -> Components:
    raid_config = raid_cfg()

    users = users or []

    def filter_users(
        players: list[model.RaidUser], role: str, has_cleared: bool
    ) -> list[model.RaidUser]:
        return list(
            filter(lambda u: u.role == role and u.has_cleared == has_cleared, players)
        )

    def format_user(u: model.RaidUser) -> str:
        return f"<@{u.discord_id}>"

    dps_need_clear_list = filter_users(users, USER_ROLE_DPS, False)
    dps_cleared_list = filter_users(users, USER_ROLE_DPS, True)
    tank_need_clear_list = filter_users(users, USER_ROLE_TANK, False)
    tank_cleared_list = filter_users(users, USER_ROLE_TANK, True)
    support_need_clear_list = filter_users(users, USER_ROLE_SUPPORT, False)
    support_cleared_list = filter_users(users, USER_ROLE_SUPPORT, True)

    dps_need_clear = " ".join(format_user(user) for user in dps_need_clear_list)
    dps_cleared = " ".join(format_user(user) for user in dps_cleared_list)
    dps_separator = raid_config.emoji.has_cleared if dps_cleared else ""
    tank_need_clear = " ".join(format_user(user) for user in tank_need_clear_list)
    tank_cleared = " ".join(format_user(user) for user in tank_cleared_list)
    tank_separator = raid_config.emoji.has_cleared if tank_cleared else ""
    support_need_clear = " ".join(format_user(user) for user in support_need_clear_list)
    support_cleared = " ".join(format_user(user) for user in support_cleared_list)
    support_separator = raid_config.emoji.has_cleared if support_cleared else ""

    total_users = len(users)
    total_dps = len(dps_need_clear_list) + len(dps_cleared_list)
    total_tank = len(tank_need_clear_list) + len(tank_cleared_list)
    total_support = len(support_need_clear_list) + len(support_cleared_list)
    total_cleared = (
        len(dps_cleared_list) + len(tank_cleared_list) + len(support_cleared_list)
    )

    raid_message_link = ""

    if guild_id and channel_id and message_id:
        raid_message_link = (
            f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
        )

    template_values: dict[str, object] = {
        "when": when,
        "title": title,
        "host_mention": f"<@{host_discord_id}>",
        "host_username": host_name,
        "host_uid": host_uid,
        "dps_emoji": raid_config.emoji.dps,
        "tank_emoji": raid_config.emoji.tank,
        "support_emoji": raid_config.emoji.support,
        "has_cleared_emoji": raid_config.emoji.has_cleared,
        "dps_need_clear": dps_need_clear,
        "dps_separator": dps_separator,
        "dps_cleared": dps_cleared,
        "tank_need_clear": tank_need_clear,
        "tank_separator": tank_separator,
        "tank_cleared": tank_cleared,
        "support_need_clear": support_need_clear,
        "support_separator": support_separator,
        "support_cleared": support_cleared,
        "raid_message_link": raid_message_link,
        "total": total_users,
        "dps_total": total_dps,
        "tank_total": total_tank,
        "support_total": total_support,
        "total_cleared": total_cleared,
    }

    message = raid_config.raid_message_template.format_map(template_values)

    components = [
        TextDisplayComponentBuilder(content=message),
        MessageActionRowBuilder(
            components=[
                InteractiveButtonBuilder(
                    custom_id=RAID_ROLE_DPS,
                    label=total_dps,
                    emoji=Emoji.parse(raid_config.emoji.dps),
                    style=ButtonStyle.SECONDARY,
                ),
                InteractiveButtonBuilder(
                    custom_id=RAID_ROLE_TANK,
                    label=total_tank,
                    emoji=Emoji.parse(raid_config.emoji.tank),
                    style=ButtonStyle.SECONDARY,
                ),
                InteractiveButtonBuilder(
                    custom_id=RAID_ROLE_SUPPORT,
                    label=total_support,
                    emoji=Emoji.parse(raid_config.emoji.support),
                    style=ButtonStyle.SECONDARY,
                ),
                InteractiveButtonBuilder(
                    custom_id=RAID_CLEARED,
                    label=total_cleared,
                    emoji=Emoji.parse(raid_config.emoji.has_cleared),
                    style=ButtonStyle.SECONDARY,
                ),
                InteractiveButtonBuilder(
                    custom_id=RAID_SIGNOFF,
                    emoji=Emoji.parse(raid_config.emoji.sign_off),
                    style=ButtonStyle.SECONDARY,
                ),
            ]
        ),
    ]

    return components


def build_raid_ping(
    guild_id: Snowflakeish,
    channel_id: Snowflakeish,
    message_id: Snowflakeish,
    when: int,
    title: str,
    host_discord_id: int,
    users: list[model.RaidUser] | None = None,
    host_name: str | None = None,
    host_uid: str | None = None,
) -> Components:
    raid_config = raid_cfg()

    users = users or []

    def filter_users(
        usrlist: list[model.RaidUser], role: str, has_cleared: bool
    ) -> list[model.RaidUser]:
        return list(
            filter(
                lambda u: u.role == role
                and (has_cleared is None or u.has_cleared == has_cleared),
                usrlist,
            )
        )

    def format_user(u: model.RaidUser) -> str:
        return f"<@{u.discord_id}>"

    dps_need_clear_list = filter_users(users, USER_ROLE_DPS, False)
    dps_cleared_list = filter_users(users, USER_ROLE_DPS, True)
    tank_need_clear_list = filter_users(users, USER_ROLE_TANK, False)
    tank_cleared_list = filter_users(users, USER_ROLE_TANK, True)
    support_need_clear_list = filter_users(users, USER_ROLE_SUPPORT, False)
    support_cleared_list = filter_users(users, USER_ROLE_SUPPORT, True)

    raid_users = " ".join(format_user(user) for user in users)
    dps_need_clear = " ".join(format_user(user) for user in dps_need_clear_list)
    dps_cleared = " ".join(format_user(user) for user in dps_cleared_list)
    dps_separator = raid_config.emoji.has_cleared if dps_cleared else ""
    tank_need_clear = " ".join(format_user(user) for user in tank_need_clear_list)
    tank_cleared = " ".join(format_user(user) for user in tank_cleared_list)
    tank_separator = raid_config.emoji.has_cleared if tank_cleared else ""
    support_need_clear = " ".join(format_user(user) for user in support_need_clear_list)
    support_cleared = " ".join(format_user(user) for user in support_cleared_list)
    support_separator = raid_config.emoji.has_cleared if support_cleared else ""

    total_users = len(users)
    total_dps = len(dps_need_clear_list) + len(dps_cleared_list)
    total_tank = len(tank_need_clear_list) + len(tank_cleared_list)
    total_support = len(support_need_clear_list) + len(support_cleared_list)
    total_cleared = (
        len(dps_cleared_list) + len(tank_cleared_list) + len(support_cleared_list)
    )

    template_values: dict[str, object] = {
        "when": when,
        "title": title,
        "host_mention": f"<@{host_discord_id}>",
        "host_username": host_name,
        "host_uid": host_uid,
        "dps_emoji": raid_config.emoji.dps,
        "tank_emoji": raid_config.emoji.tank,
        "support_emoji": raid_config.emoji.support,
        "has_cleared_emoji": raid_config.emoji.has_cleared,
        "dps_users": f"{dps_need_clear} {dps_separator} {dps_cleared}",
        "tank_users": f"{tank_need_clear} {tank_separator} {tank_cleared}",
        "support_users": f"{support_need_clear} {support_separator} {support_cleared}",
        "users": raid_users,
        "raid_message_link": f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}",
        "total": total_users,
        "dps_total": total_dps,
        "tank_total": total_tank,
        "support_total": total_support,
        "total_cleared": total_cleared,
    }

    message = raid_config.raid_ping_template.format_map(template_values)

    components = [TextDisplayComponentBuilder(content=message)]

    return components


def build_raid_removal_message(
    guild_id: Snowflakeish,
    channel_id: Snowflakeish,
    message_id: Snowflakeish,
    raid_removal_reason: str,
    when: int,
    title: str,
    host_discord_id: int,
    users: list[model.RaidUser] | None = None,
    host_name: str | None = None,
    host_uid: str | None = None,
) -> Components:
    raid_config = raid_cfg()

    users = users or []

    def filter_users(
        usrlist: list[model.RaidUser], role: str, has_cleared: bool
    ) -> list[model.RaidUser]:
        return list(
            filter(
                lambda u: u.role == role
                and (has_cleared is None or u.has_cleared == has_cleared),
                usrlist,
            )
        )

    def format_user(u: model.RaidUser) -> str:
        return f"<@{u.discord_id}>"

    dps_need_clear_list = filter_users(users, USER_ROLE_DPS, False)
    dps_cleared_list = filter_users(users, USER_ROLE_DPS, True)
    tank_need_clear_list = filter_users(users, USER_ROLE_TANK, False)
    tank_cleared_list = filter_users(users, USER_ROLE_TANK, True)
    support_need_clear_list = filter_users(users, USER_ROLE_SUPPORT, False)
    support_cleared_list = filter_users(users, USER_ROLE_SUPPORT, True)

    raid_users = " ".join(format_user(user) for user in users)
    dps_need_clear = " ".join(format_user(user) for user in dps_need_clear_list)
    dps_cleared = " ".join(format_user(user) for user in dps_cleared_list)
    dps_separator = raid_config.emoji.has_cleared if dps_cleared else ""
    tank_need_clear = " ".join(format_user(user) for user in tank_need_clear_list)
    tank_cleared = " ".join(format_user(user) for user in tank_cleared_list)
    tank_separator = raid_config.emoji.has_cleared if tank_cleared else ""
    support_need_clear = " ".join(format_user(user) for user in support_need_clear_list)
    support_cleared = " ".join(format_user(user) for user in support_cleared_list)
    support_separator = raid_config.emoji.has_cleared if support_cleared else ""

    total_users = len(users)
    total_dps = len(dps_need_clear_list) + len(dps_cleared_list)
    total_tank = len(tank_need_clear_list) + len(tank_cleared_list)
    total_support = len(support_need_clear_list) + len(support_cleared_list)
    total_cleared = (
        len(dps_cleared_list) + len(tank_cleared_list) + len(support_cleared_list)
    )

    template_values: dict[str, object] = {
        "when": when,
        "title": title,
        "host_mention": f"<@{host_discord_id}>",
        "host_username": host_name,
        "host_uid": host_uid,
        "dps_emoji": raid_config.emoji.dps,
        "tank_emoji": raid_config.emoji.tank,
        "support_emoji": raid_config.emoji.support,
        "has_cleared_emoji": raid_config.emoji.has_cleared,
        "dps_users": f"{dps_need_clear} {dps_separator} {dps_cleared}",
        "tank_users": f"{tank_need_clear} {tank_separator} {tank_cleared}",
        "support_users": f"{support_need_clear} {support_separator} {support_cleared}",
        "users": raid_users,
        "raid_message_link": f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}",
        "total": total_users,
        "dps_total": total_dps,
        "tank_total": total_tank,
        "support_total": total_support,
        "total_cleared": total_cleared,
        "raid_removal_reason": raid_removal_reason,
    }

    message = raid_config.raid_removal_dm_template.format_map(template_values)

    components = [TextDisplayComponentBuilder(content=message)]

    return components


def build_initial_thread_message(
    guild_id: Snowflakeish,
    channel_id: Snowflakeish,
    message_id: Snowflakeish,
) -> Components:
    raid_config = raid_cfg()

    template_values: dict[str, object] = {
        "raid_message_link": f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}",
    }

    message = raid_config.raid_initial_thread_message_template.format_map(
        template_values
    )

    components = [TextDisplayComponentBuilder(content=message)]

    return components


@plugin.listen()
async def _(event: ComponentInteractionCreateEvent):
    itx = event.interaction

    if itx.guild_id is None or itx.member is None:
        return
    if itx.message is None:
        return

    error = None

    with db().sm.begin() as session:
        raid = get_raid_by_message_id(session, itx.guild_id, itx.message.id)

        if raid is None:
            return

        user = get_raid_user_by_discord_id(session, raid.id, itx.member.id)

        try:
            if user is None:
                if itx.custom_id.startswith(RAID_ROLE_PREFIX):
                    create_raid_user(
                        session,
                        raid.id,
                        itx.member.id,
                        itx.custom_id[len(RAID_ROLE_PREFIX) + 1 :],
                        False,
                    )
                else:
                    error = "\N{CROSS MARK} Please select a role first!"
            else:
                if itx.custom_id.startswith(RAID_ROLE_PREFIX):
                    edit_raid_user(
                        session,
                        raid.id,
                        user.discord_id,
                        role=itx.custom_id[len(RAID_ROLE_PREFIX) + 1 :],
                    )
                elif itx.custom_id == RAID_CLEARED:
                    edit_raid_user(
                        session,
                        raid.id,
                        user.discord_id,
                        has_cleared=not user.has_cleared,
                    )
                elif itx.custom_id == RAID_SIGNOFF:
                    delete_raid_user_by_discord_id(session, raid.id, user.discord_id)
                else:
                    error = ("\N{CROSS MARK} Invalid action!",)
        except ValueError as e:
            print(f"Failed to update raid user: {e}")
            return
        except IndexError as e:
            print(f"Failed to update raid user: {e}")
            return
        raid_message = build_raid_message(
            raid.when,
            raid.title,
            raid.host_discord_id,
            raid.users,
            raid.host_username,
            raid.host_uid,
            raid.guild_id,
            raid.channel_id,
            raid.message_id,
        )
        user_mentions = [raid.host_discord_id] + [
            user.discord_id for user in raid.users
        ]

    if error is not None:
        await itx.create_initial_response(
            ResponseType.MESSAGE_CREATE,
            content=error,
            flags=MessageFlag.EPHEMERAL,
        )
        return

    await itx.create_initial_response(
        ResponseType.MESSAGE_UPDATE,
        components=raid_message,
        user_mentions=user_mentions,
    )


async def cleanup_deleted_raids():
    to_be_deleted = []

    with db().sm.begin() as session:
        raids = get_all_raids(session)

        for raid in raids:
            to_be_deleted.append(
                {
                    "channel_id": raid.channel_id,
                    "message_id": raid.message_id,
                    "guild_id": raid.guild_id,
                }
            )

    for raid in to_be_deleted:
        try:
            await plugin.client.rest.fetch_message(
                raid["channel_id"], raid["message_id"]
            )
        except NotFoundError:
            with db().sm.begin() as session:
                delete_raid_by_message_id(
                    raid_scheduler, session, raid["guild_id"], raid["message_id"]
                )
        except ForbiddenError:
            continue


async def raid_ping(raid_id: int) -> None:
    with db().sm.begin() as session:
        try:
            raid_scheduler.remove_job(f"{raid_id}")
        except JobLookupError:
            pass

        raid = session.get(model.Raid, raid_id)

        if raid is None:
            return

        channel_id = raid.channel_id
        components = build_raid_ping(
            raid.guild_id,
            raid.channel_id,
            raid.message_id,
            raid.when,
            raid.title,
            raid.host_discord_id,
            raid.users,
            raid.host_username,
            raid.host_uid,
        )
        user_mentions = [raid.host_discord_id] + [
            user.discord_id for user in raid.users
        ]
    try:
        await plugin.client.rest.create_message(
            channel=channel_id,
            components=components,
            user_mentions=user_mentions,
        )
    except (ForbiddenError, NotFoundError):
        with db().sm.begin() as session:
            delete_raid_by_message_id(
                raid_scheduler, session, raid.guild_id, raid.message_id
            )
        return
    except InternalServerError:
        return


async def raid_ping_loop() -> None:
    while True:
        raid_id = await raid_queue.get()
        plugin.client.create_task(raid_ping(raid_id))


@plugin.listen()
async def _(_: StartedEvent) -> None:
    await cleanup_deleted_raids()

    raid_scheduler.add_job(
        cleanup_deleted_raids,
        IntervalTrigger(seconds=raid_cfg().raid_cleanup_interval),
        jobstore="memory",
    )

    raid_scheduler.start()

    plugin.client.create_task(raid_ping_loop())
