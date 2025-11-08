from typing import Final

from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.ext.orderinglist import OrderingList, ordering_list
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase): ...


class Guild(Base):
    __tablename__: Final = "guild"

    id: Mapped[int] = mapped_column(primary_key=True)

    pings: Mapped[OrderingList[Ping]] = relationship(
        "Ping",
        back_populates="guild",
        order_by="Ping.index",
        collection_class=ordering_list("index"),
    )
    glue: Mapped[Glue | None] = relationship("Glue", back_populates="guild")


class Ping(Base):
    __tablename__: Final = "ping"
    __table_args__: Final = (CheckConstraint("duration >= 0"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    guild_id: Mapped[int] = mapped_column(ForeignKey(Guild.id))
    index: Mapped[int] = mapped_column()

    role_id: Mapped[int] = mapped_column()
    subscribers: Mapped[int | None] = mapped_column()
    channel_id: Mapped[int] = mapped_column()
    schedule: Mapped[str] = mapped_column()
    duration: Mapped[int] = mapped_column()
    description: Mapped[str] = mapped_column()

    guild: Mapped[Guild] = relationship("Guild", back_populates="pings")


class Glue(Base):
    __tablename__: Final = "glue"

    channel_id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column()
    guild_id: Mapped[int] = mapped_column(ForeignKey(Guild.id))

    guild: Mapped[Guild] = relationship("Guild", back_populates="glue")
