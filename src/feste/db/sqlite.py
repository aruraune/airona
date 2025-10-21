from sqlalchemy import Engine, event
from sqlalchemy.engine.interfaces import DBAPIConnection


def enable_foreign_keys(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _(dbapi_connection: DBAPIConnection, _):
        # the sqlite3 driver will not set PRAGMA foreign_keys
        # if autocommit=False; set to True temporarily
        ac = dbapi_connection.autocommit
        dbapi_connection.autocommit = True

        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

        # restore previous autocommit setting
        dbapi_connection.autocommit = ac
