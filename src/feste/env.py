import functools
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
        log: bool = False

    db: Db


@functools.cache
def cfg() -> Config:
    with Path("./env/config.toml").open("rb") as f:
        return Config(**tomllib.load(f))
