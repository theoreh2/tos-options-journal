"""
SQLAlchemy database models with secure schema design.

Security architecture:
- profiles: Contains user identity, salt, and computed data_key (SHA-256 hash)
- billing: Separate table for Stripe data, strict RLS
- trades/cash_events/trade_legs: Use owner_key (hash) instead of FK to user
  - If these tables leak, attacker cannot link back to users without profiles + salt
"""

import hashlib
import secrets
from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    String,
    Text,
    Boolean,
    Integer,
    Numeric,
    Date,
    DateTime,
    ForeignKey,
    ARRAY,
    Index,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


def generate_salt() -> str:
    """Generate a random 32-byte salt, hex-encoded."""
    return secrets.token_hex(32)


def compute_data_key(user_id: str, salt: str) -> str:
    """
    Compute SHA-256 hash of user_id + salt.
    This is the opaque key used in trade tables.
    """
    data = f"{user_id}:{salt}".encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class Profile(Base):
    """
    User profile - links to Supabase auth.users.
    Contains the salt and computed data_key for anonymizing trade data.
    """
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        comment="References auth.users(id) from Supabase",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    salt: Mapped[str] = mapped_column(
        String(64),
        default=generate_salt,
        comment="Random salt for hashing user ID",
    )
    data_key: Mapped[str] = mapped_column(
        String(64),
        index=True,
        comment="SHA-256(id + salt) - used as owner_key in trade tables",
    )

    # Relationships
    billing: Mapped[Optional["Billing"]] = relationship(back_populates="profile")
    imports: Mapped[list["Import"]] = relationship(back_populates="profile")


class Billing(Base):
    """
    Billing information - separated from profile for security.
    Contains Stripe customer ID and subscription status.
    """
    __tablename__ = "billing"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        unique=True,
    )
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(255))
    subscription_status: Mapped[str] = mapped_column(
        String(50),
        default="free",
        comment="free, trialing, active, canceled, past_due",
    )
    subscription_tier: Mapped[str] = mapped_column(
        String(50),
        default="free",
        comment="free, pro",
    )
    current_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    profile: Mapped["Profile"] = relationship(back_populates="billing")


class Import(Base):
    """Record of a CSV import."""
    __tablename__ = "imports"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("profiles.id", ondelete="CASCADE"),
    )
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    source: Mapped[str] = mapped_column(
        String(50),
        comment="TOS, TASTYTRADE, IBKR",
    )
    filename: Mapped[Optional[str]] = mapped_column(String(255))
    date_from: Mapped[Optional[date]] = mapped_column(Date)
    date_to: Mapped[Optional[date]] = mapped_column(Date)
    raw_events: Mapped[int] = mapped_column(Integer, default=0)
    trades_created: Mapped[int] = mapped_column(Integer, default=0)
    trades_updated: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    profile: Mapped["Profile"] = relationship(back_populates="imports")


class Trade(Base):
    """
    A trade (one or more legs opened/closed together).

    SECURITY: Uses owner_key (SHA-256 hash) instead of direct user_id FK.
    If this table is compromised, attacker cannot link to users without
    also having the profiles table AND the per-user salt.
    """
    __tablename__ = "trades"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    owner_key: Mapped[str] = mapped_column(
        String(64),
        index=True,
        comment="SHA-256 hash - NOT a FK, cannot be joined to users",
    )
    import_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        comment="Which import created this trade (not FK for security)",
    )
    underlying: Mapped[str] = mapped_column(String(20), index=True)
    strategy: Mapped[str] = mapped_column(
        String(50),
        comment="StrategyType enum value",
    )
    spread_label: Mapped[Optional[str]] = mapped_column(
        String(50),
        comment="Raw TOS label (VERTICAL, BUTTERFLY, etc.)",
    )
    open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    close_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expiration: Mapped[Optional[date]] = mapped_column(Date)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_expired: Mapped[bool] = mapped_column(Boolean, default=False)
    open_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        comment="Net cash at open (+ = credit, - = debit)",
    )
    close_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0"),
        comment="Net cash at close",
    )
    total_fees: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0"),
    )
    realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0"),
        comment="Gross P&L before fees",
    )
    realized_pnl_net: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0"),
        comment="Net P&L after fees",
    )
    dte_at_entry: Mapped[Optional[int]] = mapped_column(Integer)
    iv_rank_at_entry: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships (within anonymized data)
    cash_events: Mapped[list["CashEvent"]] = relationship(back_populates="trade")
    legs: Mapped[list["TradeLeg"]] = relationship(back_populates="trade")

    # Dedup index: same owner + same underlying + same open time = same trade
    __table_args__ = (
        Index("ix_trades_dedup", "owner_key", "underlying", "open_time", unique=True),
    )


class CashEvent(Base):
    """
    Individual cash flow event from TOS Cash Balance section.

    SECURITY: Uses owner_key (hash) instead of user_id FK.
    """
    __tablename__ = "cash_events"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    trade_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("trades.id", ondelete="CASCADE"),
    )
    owner_key: Mapped[str] = mapped_column(
        String(64),
        index=True,
        comment="SHA-256 hash - NOT a FK",
    )
    ref: Mapped[Optional[str]] = mapped_column(
        String(50),
        comment="TOS REF# (order ID)",
    )
    event_date: Mapped[date] = mapped_column(Date)
    event_time: Mapped[Optional[str]] = mapped_column(String(20))
    event_type: Mapped[str] = mapped_column(
        String(20),
        comment="OPEN, CLOSE, EXPIRATION, ASSIGNMENT",
    )
    description: Mapped[Optional[str]] = mapped_column(Text)
    direction: Mapped[Optional[str]] = mapped_column(
        String(10),
        comment="BUY or SELL",
    )
    qty: Mapped[int] = mapped_column(Integer, default=0)
    strategy_label: Mapped[Optional[str]] = mapped_column(String(50))
    expiration: Mapped[Optional[date]] = mapped_column(Date)
    strikes: Mapped[Optional[list[Decimal]]] = mapped_column(
        ARRAY(Numeric(12, 2)),
        comment="Array of strike prices",
    )
    option_type: Mapped[Optional[str]] = mapped_column(
        String(10),
        comment="CALL or PUT",
    )
    net_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        comment="Net cash impact",
    )
    misc_fees: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    commissions: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))

    # Relationships
    trade: Mapped["Trade"] = relationship(back_populates="cash_events")


class TradeLeg(Base):
    """
    Individual leg detail from Account Trade History.

    SECURITY: Uses owner_key (hash) instead of user_id FK.
    """
    __tablename__ = "trade_legs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    trade_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("trades.id", ondelete="CASCADE"),
    )
    owner_key: Mapped[str] = mapped_column(
        String(64),
        index=True,
        comment="SHA-256 hash - NOT a FK",
    )
    side: Mapped[str] = mapped_column(
        String(10),
        comment="BUY or SELL",
    )
    qty: Mapped[int] = mapped_column(Integer)
    pos_effect: Mapped[Optional[str]] = mapped_column(
        String(20),
        comment="TO OPEN or TO CLOSE",
    )
    expiration: Mapped[Optional[date]] = mapped_column(Date)
    strike: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    option_type: Mapped[Optional[str]] = mapped_column(
        String(10),
        comment="CALL or PUT",
    )
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))

    # Relationships
    trade: Mapped["Trade"] = relationship(back_populates="legs")
