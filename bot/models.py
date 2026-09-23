from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RosterState(Base):
    __tablename__ = "roster_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fail_state: Mapped[bool] = mapped_column(Boolean, default=False)
    message_ids: Mapped[str] = mapped_column(Text, default="[]")


class PostedVzpWar(Base):
    __tablename__ = "posted_vzp_wars"

    war_id: Mapped[str] = mapped_column(Text, primary_key=True)
    message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class PlusEvent(Base):
    __tablename__ = "plus_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(Integer)
    message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    creator_id: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    need_static: Mapped[bool] = mapped_column(Boolean, default=False)
    participants_json: Mapped[str] = mapped_column(Text, default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    event_kind: Mapped[str] = mapped_column(Text, default="general")
