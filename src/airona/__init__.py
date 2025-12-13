import logging

from arc import GatewayClient
from hikari import GatewayBot, Intents

from airona.db.connection import db
from airona.db.model import Base
from airona.env import cfg, discord
from airona.ext import settings, raid


def main() -> None:
    logging.getLogger("apscheduler").setLevel(cfg().apscheduler.log_level)
    logging.getLogger("sqlalchemy.engine").setLevel(cfg().sqlalchemy.log_level)

    bot = GatewayBot(discord().token, intents=Intents.NONE)

    client = GatewayClient(bot)
    client.add_plugin(settings.plugin)
    client.add_plugin(raid.plugin)

    bot.run()


def init_db() -> None:
    db().engine.echo = True
    Base.metadata.create_all(db().engine)
