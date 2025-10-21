from typing import Final

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.ext.orderinglist import OrderingList, ordering_list
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase): ...


class Guild(Base):
    __tablename__: Final = "guild"

    id: Mapped[int] = mapped_column(primary_key=True)

    roles: Mapped[OrderingList[Role]] = relationship(
        "Role",
        back_populates="guild",
        order_by="Role.index",
        collection_class=ordering_list("index"),
    )


class Role(Base):
    __tablename__: Final = "role"
    __table_args__: Final = (UniqueConstraint("guild_id", "index"),)

    guild_id: Mapped[int] = mapped_column(ForeignKey(Guild.id), primary_key=True)
    id: Mapped[int] = mapped_column(primary_key=True)
    index: Mapped[int] = mapped_column()
    description: Mapped[str] = mapped_column()

    guild: Mapped[Guild] = relationship("Guild", back_populates="roles")
