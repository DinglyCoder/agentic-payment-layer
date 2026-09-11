from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class PaymentStatus(StrEnum):
    DETECTED = "detected"
    SCORING = "scoring"
    APPROVED = "approved"
    EXECUTED = "executed"
    RECALLED = "recalled"
    FAILED = "failed"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RegistryStatus(StrEnum):
    VERIFIED = "verified"
    WATCHLIST = "watchlist"
    UNKNOWN = "unknown"


class Payment(Base):
    __tablename__ = "payments"

    payment_id: Mapped[str] = mapped_column(String(66), primary_key=True)
    sender: Mapped[str] = mapped_column(String(42), index=True)
    receiver: Mapped[str] = mapped_column(String(42), index=True)
    amount_units: Mapped[str] = mapped_column(String(78))
    metadata_hash: Mapped[str] = mapped_column(String(66))
    description: Mapped[str] = mapped_column(String(240), default="Agent service payment")
    deposit_tx_hash: Mapped[str] = mapped_column(String(66), unique=True)
    resolution_tx_hash: Mapped[str | None] = mapped_column(String(66), nullable=True)
    block_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deposited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recall_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default=PaymentStatus.DETECTED, index=True)
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    risk_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    llm_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="sepolia")
    decision_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AgentIdentity(Base):
    __tablename__ = "agent_identities"

    address: Mapped[str] = mapped_column(String(42), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(16), default=RegistryStatus.UNKNOWN)
    trust_score: Mapped[int] = mapped_column(Integer, default=50)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
