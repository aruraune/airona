import re
from string import Template

import arc
from arc import (
    GatewayContext,
    GatewayPlugin,
    IntParams,
    Option,
    RoleParams,
    StrParams,
)
from hikari import (
    ButtonStyle,
    ComponentInteractionCreateEvent,
    ForbiddenError,
    MessageFlag,
    NotFoundError,
    ResponseType,
    Role,
    Snowflakeish,
)
from hikari.impl import (
    InteractiveButtonBuilder,
    SectionComponentBuilder,
    TextDisplayComponentBuilder,
)
from sqlalchemy import select

from feste.db import schema
from feste.db.connection import db
from feste.etc import error_handler
from feste.ext.settings import settings_group
from feste.typing import Components

plugin = GatewayPlugin(__name__)

settings_role_group = settings_group.include_subgroup("role", "Manage roles.")

MAX_ROLES = 15


@settings_role_group.include
@arc.slash_subcommand("upsert", "Upsert a role.")
async def _(
    ctx: GatewayContext,
    role: Option[Role, RoleParams("the role")],
    description: Option[str, StrParams("the description")],
    index: Option[int | None, IntParams("the index", min=0)] = None,
) -> None:
    if ctx.guild_id is None:
        return
    with db().sm.begin() as session:
        db_guild = session.get(schema.Guild, ctx.guild_id) or schema.Guild(
            id=ctx.guild_id
        )
        if db_role := session.get(schema.Role, (db_guild.id, role.id)):
            session.delete(db_role)
        db_role = schema.Role(id=role.id, description=description)
        length = len(db_guild.roles)
        if index is None:
            index = length
        if index > length:
            await ctx.respond(
                "\N{CROSS MARK} invalid index", flags=MessageFlag.EPHEMERAL
            )
            return
        if index == length and length >= MAX_ROLES:
            await ctx.respond(
                f"\N{CROSS MARK} maximum of {MAX_ROLES} roles",
                flags=MessageFlag.EPHEMERAL,
            )
            return
        for i in range(length - 1, index - 1, -1):
            db_guild.roles[i].index += 1
        db_role.index = index
        db_guild.roles.append(db_role)
        session.add(db_guild)
    await ctx.respond(
        "\N{WHITE HEAVY CHECK MARK} upserted role", flags=MessageFlag.EPHEMERAL
    )


@settings_role_group.include
@arc.slash_subcommand("remove", "Remove a role.")
async def _(
    ctx: GatewayContext,
    index: Option[int, IntParams("the index", min=0)],
) -> None:
    if ctx.guild_id is None:
        return
    with db().sm.begin() as session:
        db_role = session.scalar(
            select(schema.Role).where(
                (schema.Role.guild_id == ctx.guild_id) & (schema.Role.index == index)
            )
        )
        if db_role is None:
            await ctx.respond(
                f"\N{CROSS MARK} no role with index {index}",
                flags=MessageFlag.EPHEMERAL,
            )
            return
        session.delete(db_role)
    await ctx.respond(
        "\N{WHITE HEAVY CHECK MARK} deleted role", flags=MessageFlag.EPHEMERAL
    )


def build_rolemenu(guild_id: Snowflakeish) -> Components:
    components = []
    with db().sm() as session:
        db_guild = session.get(schema.Guild, guild_id)
        if db_guild is None or len(db_guild.roles) == 0:
            return [TextDisplayComponentBuilder(content="*No roles configured.*")]
        for db_role in db_guild.roles:
            components.append(
                SectionComponentBuilder(
                    components=[
                        TextDisplayComponentBuilder(
                            content=Template(db_role.description).safe_substitute(
                                role=f"<@&{db_role.id}>",
                            )
                        )
                    ],
                    accessory=InteractiveButtonBuilder(
                        custom_id=f"rolemenu:{db_role.index}",
                        label="Toggle",
                        style=ButtonStyle.PRIMARY,
                    ),
                )
            )
    return components


@plugin.listen()
async def _(event: ComponentInteractionCreateEvent) -> None:
    itx = event.interaction
    if itx.guild_id is None or itx.member is None:
        return
    if (match := re.fullmatch(r"rolemenu:(\d+)", itx.custom_id)) is None:
        return
    index = int(match.group(1))
    with db().sm() as session:
        db_guild = session.get(schema.Guild, itx.guild_id)
        if db_guild is None:
            await itx.create_initial_response(
                ResponseType.MESSAGE_CREATE,
                "\N{CROSS MARK} No such guild.",
                flags=MessageFlag.EPHEMERAL,
            )
            return
        try:
            db_role = db_guild.roles[index]
        except KeyError:
            await itx.create_initial_response(
                ResponseType.MESSAGE_CREATE,
                "\N{CROSS MARK} No such role.",
                flags=MessageFlag.EPHEMERAL,
            )
            return
        try:
            if db_role.id in itx.member.role_ids:
                await itx.member.remove_role(db_role.id)
                await itx.create_initial_response(
                    ResponseType.MESSAGE_CREATE,
                    f"Removed <@&{db_role.id}>.",
                    flags=MessageFlag.EPHEMERAL,
                )
            else:
                await itx.member.add_role(db_role.id)
                await itx.create_initial_response(
                    ResponseType.MESSAGE_CREATE,
                    f"Added <@&{db_role.id}>.",
                    flags=MessageFlag.EPHEMERAL,
                )
        except ForbiddenError:
            await itx.create_initial_response(
                ResponseType.MESSAGE_CREATE,
                "\N{CROSS MARK} Missing permissions.",
                flags=MessageFlag.EPHEMERAL,
            )
            return
        except NotFoundError:
            await itx.create_initial_response(
                ResponseType.MESSAGE_CREATE,
                "\N{CROSS MARK} Role not found.",
                flags=MessageFlag.EPHEMERAL,
            )
            return


@plugin.include
@arc.with_hook(arc.guild_only)
@arc.slash_command("role", "Select roles.")
async def slash_role(ctx: GatewayContext) -> None:
    if ctx.guild_id is None:
        return
    await ctx.respond(
        components=build_rolemenu(ctx.guild_id), flags=MessageFlag.EPHEMERAL
    )


slash_role.set_error_handler(error_handler.guild_only)
