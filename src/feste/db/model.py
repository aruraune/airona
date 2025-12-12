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
        collection_class=ordering_list("index"),
        order_by="Ping.index",
        back_populates="guild",
        cascade="save-update, merge, delete",
        passive_deletes=True,
    )
    glue: Mapped[Glue | None] = relationship(
        "Glue",
        back_populates="guild",
        cascade="save-update, merge, delete",
        passive_deletes=True,
    )
    raids: Mapped[OrderingList[Raid]] = relationship(
        "Raid",
        collection_class=ordering_list("index"),
        order_by="Raid.index",
        back_populates="guild",
        cascade="save-update, merge, delete",
        passive_deletes=True,
    )


class Ping(Base):
    __tablename__: Final = "ping"
    __table_args__: Final = (CheckConstraint("duration >= 0"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    guild_id: Mapped[int] = mapped_column(ForeignKey(Guild.id, ondelete="CASCADE"))
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
    guild_id: Mapped[int] = mapped_column(ForeignKey(Guild.id, ondelete="CASCADE"))

    guild: Mapped[Guild] = relationship("Guild", back_populates="glue")


class Raid(Base):
    __tablename__: Final = "raid"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    index: Mapped[int] = mapped_column()

    guild_id: Mapped[int] = mapped_column(ForeignKey(Guild.id, ondelete="CASCADE"))

    channel_id: Mapped[int] = mapped_column()
    message_id: Mapped[int] = mapped_column()

    host_mention: Mapped[str] = mapped_column()
    when: Mapped[int] = mapped_column()
    title: Mapped[str] = mapped_column()

    guild: Mapped[Guild] = relationship("Guild", back_populates="raids")
    users: Mapped[list[RaidUser]] = relationship("RaidUser", back_populates="raid", passive_deletes=True)


class RaidUser(Base):
    __tablename__: Final = "raid_user"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    raid_id: Mapped[int] = mapped_column(ForeignKey(Raid.id, ondelete="CASCADE"))

    discord_id: Mapped[int] = mapped_column()
    role: Mapped[str] = mapped_column()
    has_cleared: Mapped[bool] = mapped_column()

    raid: Mapped[Raid] = relationship("Raid", back_populates="users")
