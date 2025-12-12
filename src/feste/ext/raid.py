import arc
import hikari
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
    StartedEvent
)
from hikari.impl import TextDisplayComponentBuilder, MessageActionRowBuilder, InteractiveButtonBuilder

from feste.db import model
from feste.db.connection import db
from feste.env import raid_cfg
from feste.lib.raid import (
    create_raid,
    get_raid_by_message_id,
    get_all_raids,
    delete_raid_by_message_id,
    create_raid_user,
    get_raid_user_by_discord_id,
    edit_raid_user,
    delete_raid_user_by_discord_id,
)
from feste.typing import Components


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
    users: set[model.RaidUser] | None = None,
    host_name: str | None = None,
    host_uid: str | None = None,
) -> Components:
    raid_template = raid_cfg()

    users = users or []

    def format_user(u: model.RaidUser) -> str:
        return f"<@{u.discord_id}>{raid_template.emoji.has_cleared if u.has_cleared else ''}"

    template_values: dict[str, object] = {
        "when": when,
        "title": title,
        "host_mention": host_mention,
        "dps_emoji": raid_template.emoji.dps,
        "tank_emoji": raid_template.emoji.tank,
        "support_emoji": raid_template.emoji.support,
        "has_cleared_emoji": raid_template.emoji.has_cleared,
        "dps_users": " ".join(format_user(user) for user in users if user.role == USER_ROLE_DPS),
        "tank_users": " ".join(format_user(user) for user in users if user.role == USER_ROLE_TANK),
        "support_users": " ".join(format_user(user) for user in users if user.role == USER_ROLE_SUPPORT),
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
                    emoji=raid_template.emoji.dps,
                    style=ButtonStyle.PRIMARY,
                ),
                InteractiveButtonBuilder(
                    custom_id=RAID_ROLE_TANK,
                    emoji=raid_template.emoji.tank,
                    style=ButtonStyle.PRIMARY,
                ),
                InteractiveButtonBuilder(
                    custom_id=RAID_ROLE_SUPPORT,
                    emoji=raid_template.emoji.support,
                    style=ButtonStyle.PRIMARY,
                ),
                InteractiveButtonBuilder(
                    custom_id=RAID_CLEARED,
                    emoji=raid_template.emoji.has_cleared,
                    style=ButtonStyle.SECONDARY,
                ),
                InteractiveButtonBuilder(
                    custom_id=RAID_SIGNOFF,
                    emoji=raid_template.emoji.sign_off,
                    style=ButtonStyle.DANGER,
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
