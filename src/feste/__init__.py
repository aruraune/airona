import logging

from arc import GatewayClient
from hikari import GatewayBot

from feste.db.connection import db
from feste.db.model import Base
from feste.env import cfg, discord
from feste.ext import glue, ping, ping_select, settings


def main() -> None:
    logging.getLogger("sqlalchemy.engine").setLevel(cfg().sqlalchemy.log_level)

    bot = GatewayBot(discord().token)

    client = GatewayClient(bot)
    client.add_plugin(glue.plugin)
    client.add_plugin(ping.plugin)
    client.add_plugin(ping_select.plugin)
    client.add_plugin(settings.plugin)

    bot.run()


def init_db() -> None:
    db().engine.echo = True
    Base.metadata.create_all(db().engine)
