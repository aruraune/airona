from typing import Final

from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase): ...


class Guild(Base):
    __tablename__: Final = "guild"

    id: Mapped[int] = mapped_column(primary_key=True)

    glue: Mapped[Glue | None] = relationship("Glue", back_populates="guild")


class Glue(Base):
    __tablename__: Final = "glue"

    channel_id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column()
    guild_id: Mapped[int] = mapped_column(ForeignKey(Guild.id))

    guild: Mapped[Guild] = relationship("Guild", back_populates="glue")
