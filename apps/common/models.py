from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    Time,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class LeadStatus(str, enum.Enum):
    NEW = "NEW"
    WAITING_REPLY = "WAITING_REPLY"
    IN_DIALOG = "IN_DIALOG"
    QUALIFIED = "QUALIFIED"
    WON = "WON"
    LOST = "LOST"
    DNC = "DNC"
    ERROR = "ERROR"


class MessageDirection(str, enum.Enum):
    IN = "IN"
    OUT = "OUT"


class Account(Base):
    __tablename__ = "accounts"

    account_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    timezone: Mapped[str] = mapped_column(
        Text, nullable=False, default="Europe/Berlin", server_default=text("'Europe/Berlin'")
    )
    max_messages_per_day: Mapped[int] = mapped_column(Integer, nullable=False)
    max_new_chats_per_day: Mapped[int] = mapped_column(Integer, nullable=False)
    min_delay_sec: Mapped[int] = mapped_column(Integer, nullable=False)
    max_delay_sec: Mapped[int] = mapped_column(Integer, nullable=False)
    quiet_hours_start: Mapped[time | None] = mapped_column(Time)
    quiet_hours_end: Mapped[time | None] = mapped_column(Time)

    leads: Mapped[list[Lead]] = relationship(back_populates="account")


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (
        Index("ix_leads_account_status_next_action", "account_id", "status", "next_action_at"),
        Index(
            "uq_leads_account_tg_peer_id_not_null",
            "account_id",
            "tg_peer_id",
            unique=True,
            postgresql_where=text("tg_peer_id IS NOT NULL"),
        ),
    )

    lead_id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(
        String, ForeignKey("accounts.account_id"), nullable=False
    )
    tg_peer_id: Mapped[int | None] = mapped_column(BigInteger)
    tg_username: Mapped[str | None] = mapped_column(Text)
    consent: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    stage: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    attempts_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_message_in: Mapped[str | None] = mapped_column(Text)
    last_message_out: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    qualification_json: Mapped[dict | None] = mapped_column(JSONB().with_variant(JSON(), "sqlite"))
    dnc: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    account: Mapped[Account] = relationship(back_populates="leads")
    messages: Mapped[list[Message]] = relationship(back_populates="lead")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_lead_id_ts", "lead_id", "ts"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[str] = mapped_column(String, ForeignKey("leads.lead_id"), nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    tg_message_id: Mapped[int | None] = mapped_column(BigInteger)
    meta_json: Mapped[dict | None] = mapped_column(JSONB().with_variant(JSON(), "sqlite"))

    lead: Mapped[Lead] = relationship(back_populates="messages")


class DailyCounter(Base):
    __tablename__ = "daily_counters"
    __table_args__ = (PrimaryKeyConstraint("account_id", "date", name="pk_daily_counters"),)

    account_id: Mapped[str] = mapped_column(
        String, ForeignKey("accounts.account_id"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    sent_messages: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    new_threads: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
