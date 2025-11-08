import logging

from arc import GatewayClient
from hikari import GatewayBot, Intents

from feste.db.connection import db
from feste.db.model import Base
from feste.env import cfg, discord
from feste.ext import glue, menu, ping, settings, subscribers


def main() -> None:
    logging.getLogger("apscheduler").setLevel(cfg().apscheduler.log_level)
    logging.getLogger("sqlalchemy.engine").setLevel(cfg().sqlalchemy.log_level)

    bot = GatewayBot(discord().token, intents=Intents.GUILDS | Intents.GUILD_MEMBERS)

    client = GatewayClient(bot)
    client.add_plugin(glue.plugin)
    client.add_plugin(ping.plugin)
    client.add_plugin(menu.plugin)
    client.add_plugin(subscribers.plugin)
    client.add_plugin(settings.plugin)

    bot.run()


def init_db() -> None:
    db().engine.echo = True
    Base.metadata.create_all(db().engine)
