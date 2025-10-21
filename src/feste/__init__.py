import logging

from arc import GatewayClient
from hikari import GatewayBot

from feste.db.connection import db
from feste.db.schema import Base
from feste.env import cfg, discord
from feste.ext import role, settings


def main() -> None:
    if cfg().db.log:
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)

    bot = GatewayBot(discord().token)

    client = GatewayClient(bot)
    client.add_plugin(role.plugin)
    client.add_plugin(settings.plugin)

    bot.run()


def init_db() -> None:
    db().engine.echo = True
    Base.metadata.create_all(db().engine)
