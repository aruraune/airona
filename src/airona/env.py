import functools
import logging
import tomllib
from pathlib import Path

from pydantic import BaseModel


class Discord(BaseModel):
    token: str


@functools.cache
def discord() -> Discord:
    with Path("./env/discord.toml").open("rb") as f:
        return Discord(**tomllib.load(f))


class Config(BaseModel):
    class Db(BaseModel):
        url: str

    db: Db

    class Apscheduler(BaseModel):
        jobstore: str
        log_level: int = logging.WARNING

    apscheduler: Apscheduler

    class Sqlalchemy(BaseModel):
        log_level: int = logging.WARNING

    sqlalchemy: Sqlalchemy


@functools.cache
def cfg() -> Config:
    with Path("./env/config.toml").open("rb") as f:
        return Config(**tomllib.load(f))


class RaidConfig(BaseModel):
    raid_cleanup_interval: int

    raid_message_template: str
    raid_ping_template: str

    class Emoji(BaseModel):
        dps: str
        tank: str
        support: str
        has_cleared: str
        sign_off: str

    emoji: Emoji


@functools.cache
def raid_cfg() -> RaidConfig:
    with Path("./env/raid.toml").open("rb") as f:
        return RaidConfig(**tomllib.load(f))
