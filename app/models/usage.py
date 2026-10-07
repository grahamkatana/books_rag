"""What the AI providers were asked to do, what it cost, and what the admin has told us about prices and credit."""

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # chat | embed | cross_check | context | verify | extract
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated: Mapped[bool] = mapped_column(Boolean, default=False)


class ModelPrice(Base):
    __tablename__ = "model_prices"

    provider: Mapped[str] = mapped_column(String(40), primary_key=True)
    model: Mapped[str] = mapped_column(String(100), primary_key=True)
    input_per_million: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    output_per_million: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    note: Mapped[str] = mapped_column(String(200), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class ProviderCredit(Base):
    __tablename__ = "provider_credits"

    provider: Mapped[str] = mapped_column(String(40), primary_key=True)
    amount_usd: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
