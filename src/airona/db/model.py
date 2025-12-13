from typing import Final

from sqlalchemy import ForeignKey
from sqlalchemy.ext.orderinglist import OrderingList, ordering_list
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase): ...


class Guild(Base):
    __tablename__: Final = "guild"

    id: Mapped[int] = mapped_column(primary_key=True)

    raids: Mapped[OrderingList[Raid]] = relationship(
        "Raid",
        collection_class=ordering_list("index"),
        order_by="Raid.index",
        back_populates="guild",
        cascade="save-update, merge, delete",
        passive_deletes=True,
    )


class Raid(Base):
    __tablename__: Final = "raid"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    index: Mapped[int] = mapped_column()

    guild_id: Mapped[int] = mapped_column(ForeignKey(Guild.id, ondelete="CASCADE"))

    channel_id: Mapped[int] = mapped_column()
    message_id: Mapped[int] = mapped_column()

    host_discord_id: Mapped[int] = mapped_column()
    host_username: Mapped[str] = mapped_column()
    host_uid: Mapped[str] = mapped_column()
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
