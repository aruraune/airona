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
    glue_interval: int
    subscribers_interval: int

    class Db(BaseModel):
        url: str

    db: Db

    class Apscheduler(BaseModel):
        jobstore: str

    apscheduler: Apscheduler

    class Sqlalchemy(BaseModel):
        log_level: int = logging.WARNING

    sqlalchemy: Sqlalchemy


@functools.cache
def cfg() -> Config:
    with Path("./env/config.toml").open("rb") as f:
        return Config(**tomllib.load(f))
