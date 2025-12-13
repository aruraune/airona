import functools
from typing import Final

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from airona.db import sqlite
from airona.env import cfg


class DbConnection:
    def __init__(self) -> None:
        self.engine: Final = create_engine(cfg().db.url)
        sqlite.enable_foreign_keys(self.engine)
        self.sm: Final = sessionmaker(self.engine)


@functools.cache
def db() -> DbConnection:
    return DbConnection()
