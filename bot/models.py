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


class ApplicationQuestion(Base):
    __tablename__ = "application_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order: Mapped[int] = mapped_column(Integer, default=1)
    question: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(Integer, unique=True)
    applicant_id: Mapped[int] = mapped_column(Integer)
    handler_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="open")
    answers_json: Mapped[str] = mapped_column(Text, default="[]")
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Birthday(Base):
    __tablename__ = "birthdays"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)


class VzpDefense(Base):
    """Забив на нас: чтобы не слать уведомление об одном бое дважды."""

    __tablename__ = "vzp_defenses"
    war_id: Mapped[str] = mapped_column(Text, primary_key=True)
    attacker: Mapped[str] = mapped_column(Text, default="")
    territory: Mapped[str] = mapped_column(Text, default="")
    noticed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


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
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
