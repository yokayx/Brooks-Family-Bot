from sqlalchemy import Boolean, Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RosterState(Base):
    __tablename__ = "roster_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fail_state: Mapped[bool] = mapped_column(Boolean, default=False)
    message_ids: Mapped[str] = mapped_column(Text, default="[]")
