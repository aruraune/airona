import arc
import hikari
import re
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import UTC
from arc import GatewayPlugin, GatewayContext, AutodeferMode, Option, IntParams, StrParams, UserParams
from hikari import (
    MessageFlag,
    ForbiddenError,
    ButtonStyle,
    ComponentInteractionCreateEvent,
    ResponseType,
    Snowflakeish,
    GuildMessageDeleteEvent,
    NotFoundError,
    StartedEvent,
    CustomEmoji
)
from hikari.impl import TextDisplayComponentBuilder, MessageActionRowBuilder, InteractiveButtonBuilder

from airona.db import model
from airona.db.connection import db
from airona.env import raid_cfg
from airona.lib.raid import (
    create_raid,
    get_raid_by_message_id,
    get_all_raids,
    delete_raid_by_message_id,
    create_raid_user,
    get_raid_user_by_discord_id,
    edit_raid_user,
    delete_raid_user_by_discord_id,
)
from airona.typing import Components


plugin = GatewayPlugin(__name__)

raid_group = plugin.include_slash_group(
    "raid",
    "Manage raids.",
    autodefer=AutodeferMode.EPHEMERAL
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


@raid_group.include
@arc.slash_subcommand("create", "Create a new raid.")
async def _(
    ctx: GatewayContext,
    host: Option[hikari.User, UserParams("the host of the raid.")],
    when: Option[int, IntParams("the time when the raid will start (timestamp, use hammertime.cyou).")],
    title: Option[str, StrParams("the title of the raid announcement (e.g. All raids, Light NM).")],
    index: Option[int | None, IntParams("the index to insert the raid at.")] = None,
) -> None:
    if ctx.guild_id is None:
        return
    try:
        with db().sm.begin() as session:
            try:
                # TODO: Obtain host name and uid
                message = await plugin.client.rest.create_message(
                    ctx.channel_id,
                    components=build_raid_message(when, title, host.mention)
                )
                await plugin.client.rest.create_message_thread(
                    ctx.channel_id,
                    message.id,
                    f"{title}"
                )
            except ForbiddenError:
                await ctx.respond(
                    "\N{CROSS MARK} Missing `Send Messages` permission.",
                    flags=MessageFlag.EPHEMERAL,
                )
                return
            create_raid(
                session,
                ctx.guild_id,
                ctx.channel_id,
                message.id,
                host.mention,
                when,
                title,
                index)
    except ValueError as e:
        await ctx.respond(f"\N{CROSS MARK} {e}", flags=MessageFlag.EPHEMERAL)
        return
    await ctx.respond(
        content="\N{WHITE HEAVY CHECK MARK}",
        flags=MessageFlag.EPHEMERAL,
    )


async def update_raid_message(
    session: db.Session,
    guild_id: Snowflakeish,
    message_id: Snowflakeish,
):
    raid = get_raid_by_message_id(session, guild_id, message_id)

    if raid is None:
        return

    try:
        # TODO: Obtain host name and uid
        await plugin.client.rest.edit_message(
            raid.channel_id,
            message_id,
            components=build_raid_message(raid.when, raid.title, raid.host_mention, raid.users)
        )
    except NotFoundError:
        delete_raid_by_message_id(session, guild_id, message_id)
        return


def build_raid_message(
    when: int,
    title: str,
    host_mention: str,
    users: list[model.RaidUser] | None = None,
    host_name: str | None = None,
    host_uid: str | None = None,
) -> Components:
    raid_template = raid_cfg()

    users = users or []

    def filter_users(users: list[model.RaidUser], role: str, has_cleared: bool) -> list[model.RaidUser]:
        return list(filter(lambda u: u.role == role and (has_cleared is None or u.has_cleared == has_cleared), users))

    def format_user(u: model.RaidUser) -> str:
        return f"<@{u.discord_id}>"

    def convert_emoji(emoji: str | None):
        if not emoji:
            return emoji
        match = re.match(r"^<a?:(?P<name>[^:]+):(?P<id>\d+)>$", emoji)
        if match:
            try:
                return CustomEmoji(id=match.group("id"), name=match.group("name"), is_animated=emoji.startswith("<a:"))
            except Exception:
                return emoji
        return emoji

    dps_need_clear = " ".join(format_user(user) for user in filter_users(users, USER_ROLE_DPS, False))
    dps_cleared = " ".join(format_user(user) for user in filter_users(users, USER_ROLE_DPS, True))
    dps_separator = raid_template.emoji.has_cleared if dps_cleared else ""
    tank_need_clear = " ".join(format_user(user) for user in filter_users(users, USER_ROLE_TANK, False))
    tank_cleared = " ".join(format_user(user) for user in filter_users(users, USER_ROLE_TANK, True))
    tank_separator = raid_template.emoji.has_cleared if tank_cleared else ""
    support_need_clear = " ".join(format_user(user) for user in filter_users(users, USER_ROLE_SUPPORT, False))
    support_cleared = " ".join(format_user(user) for user in filter_users(users, USER_ROLE_SUPPORT, True))
    support_separator = raid_template.emoji.has_cleared if support_cleared else ""

    template_values: dict[str, object] = {
        "when": when,
        "title": title,
        "host_mention": host_mention,
        "dps_emoji": raid_template.emoji.dps,
        "tank_emoji": raid_template.emoji.tank,
        "support_emoji": raid_template.emoji.support,
        "has_cleared_emoji": raid_template.emoji.has_cleared,
        "dps_users": f"{dps_need_clear} {dps_separator} {dps_cleared}",
        "tank_users": f"{tank_need_clear} {tank_separator} {tank_cleared}",
        "support_users": f"{support_need_clear} {support_separator} {support_cleared}",
    }

    message = raid_template.template.format_map(template_values)

    components = [
        TextDisplayComponentBuilder(
            content=message
        ),
        MessageActionRowBuilder(
            components=[
                InteractiveButtonBuilder(
                    custom_id=RAID_ROLE_DPS,
                    emoji=convert_emoji(raid_template.emoji.dps),
                    style=ButtonStyle.SECONDARY,
                ),
                InteractiveButtonBuilder(
                    custom_id=RAID_ROLE_TANK,
                    emoji=convert_emoji(raid_template.emoji.tank),
                    style=ButtonStyle.SECONDARY,
                ),
                InteractiveButtonBuilder(
                    custom_id=RAID_ROLE_SUPPORT,
                    emoji=convert_emoji(raid_template.emoji.support),
                    style=ButtonStyle.SECONDARY,
                ),
                InteractiveButtonBuilder(
                    custom_id=RAID_CLEARED,
                    emoji=convert_emoji(raid_template.emoji.has_cleared),
                    style=ButtonStyle.SECONDARY,
                ),
                InteractiveButtonBuilder(
                    custom_id=RAID_SIGNOFF,
                    emoji=convert_emoji(raid_template.emoji.sign_off),
                    style=ButtonStyle.SECONDARY,
                ),
            ]
        )
    ]

    return components


@plugin.listen()
async def _(event: ComponentInteractionCreateEvent):
    itx = event.interaction

    if itx.guild_id is None or itx.member is None:
        return
    if itx.message is None:
        return

    with (db().sm.begin() as session):
        raid = get_raid_by_message_id(session, itx.guild_id, itx.message.id)

        if raid is None:
            return

        user = get_raid_user_by_discord_id(session, raid.id, itx.member.id)

        try:
            if user is None:
                if itx.custom_id.startswith(RAID_ROLE_PREFIX):
                    create_raid_user(session, raid.id, itx.member.id, itx.custom_id[len(RAID_ROLE_PREFIX) + 1:])
                else:
                    await itx.create_initial_response(
                        ResponseType.MESSAGE_CREATE,
                        "\N{CROSS MARK} Please select a role first!",
                        flags=MessageFlag.EPHEMERAL,
                    )
                    return
            else:
                if itx.custom_id.startswith(RAID_ROLE_PREFIX):
                    edit_raid_user(session, raid.id, user.discord_id, role=itx.custom_id[len(RAID_ROLE_PREFIX) + 1:])
                elif itx.custom_id == RAID_CLEARED:
                    edit_raid_user(session, raid.id, user.discord_id, has_cleared=not user.has_cleared)
                elif itx.custom_id == RAID_SIGNOFF:
                    delete_raid_user_by_discord_id(session, raid.id, user.discord_id)
                else:
                    await itx.create_initial_response(
                        ResponseType.MESSAGE_CREATE,
                        "\N{CROSS MARK} Invalid action!",
                        flags=MessageFlag.EPHEMERAL,
                    )
                    return
            await itx.create_initial_response(
                ResponseType.MESSAGE_CREATE,
                "\N{WHITE HEAVY CHECK MARK}",
                flags=MessageFlag.EPHEMERAL,
            )
        except ValueError as e:
            await itx.create_initial_response(
                ResponseType.MESSAGE_CREATE,
                f"\N{CROSS MARK} {e}",
                flags=MessageFlag.EPHEMERAL,
            )
        except IndexError as e:
            await itx.create_initial_response(
                ResponseType.MESSAGE_CREATE,
                f"\N{CROSS MARK} {e}",
                flags=MessageFlag.EPHEMERAL,
            )

        await update_raid_message(session, itx.guild_id, itx.message.id)


@plugin.listen()
async def _(event: GuildMessageDeleteEvent):
    if event.guild_id is None:
        return

    with (db().sm.begin() as session):
        delete_raid_by_message_id(session, event.guild_id, event.message_id)


async def cleanup_deleted_raids():
    with db().sm.begin() as session:
        raids = get_all_raids(session)

        for raid in raids:
            try:
                await plugin.client.rest.fetch_message(raid.channel_id, raid.message_id)
            except NotFoundError:
                delete_raid_by_message_id(session, raid.guild_id, raid.message_id)
            except ForbiddenError:
                continue


async def do_deferred() -> None:
    await cleanup_deleted_raids()


scheduler = AsyncIOScheduler(timezone=UTC)


@plugin.listen()
async def _(_: StartedEvent) -> None:
    await cleanup_deleted_raids()

    scheduler.add_job(do_deferred, IntervalTrigger(seconds=raid_cfg().raid_cleanup_interval))
    scheduler.start()
