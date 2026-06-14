"""Pydantic schemas for API request/response validation."""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict


# ============================================================================
# Trade Schemas
# ============================================================================

class CashEventSchema(BaseModel):
    """Cash event detail."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    ref: Optional[str]
    event_date: date
    event_time: Optional[str]
    event_type: str
    description: Optional[str]
    direction: Optional[str]
    qty: int
    strategy_label: Optional[str]
    expiration: Optional[date]
    strikes: Optional[list[Decimal]]
    option_type: Optional[str]
    net_price: Optional[Decimal]
    amount: Decimal
    misc_fees: Decimal
    commissions: Decimal


class TradeLegSchema(BaseModel):
    """Trade leg detail."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    side: str
    qty: int
    pos_effect: Optional[str]
    expiration: Optional[date]
    strike: Optional[Decimal]
    option_type: Optional[str]
    price: Optional[Decimal]


class TradeListItem(BaseModel):
    """Trade summary for list views."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    underlying: str
    strategy: str
    spread_label: Optional[str]
    open_time: datetime
    close_time: Optional[datetime]
    expiration: Optional[date]
    is_closed: bool
    is_expired: bool
    open_amount: Decimal
    close_amount: Decimal
    total_fees: Decimal
    realized_pnl: Decimal
    realized_pnl_net: Decimal
    dte_at_entry: Optional[int]


class TradeDetail(TradeListItem):
    """Full trade detail including legs and cash events."""
    iv_rank_at_entry: Optional[Decimal]
    notes: Optional[str]
    cash_events: list[CashEventSchema]
    legs: list[TradeLegSchema]
    created_at: datetime
    updated_at: datetime


class TradeListResponse(BaseModel):
    """Paginated trade list."""
    trades: list[TradeListItem]
    total: int
    page: int
    page_size: int


# ============================================================================
# Import Schemas
# ============================================================================

class ImportResult(BaseModel):
    """Result of a CSV import."""
    import_id: str
    source: str
    filename: Optional[str]
    date_from: Optional[date]
    date_to: Optional[date]
    raw_events: int
    trades_created: int
    trades_updated: int
    warnings: list[str]


class ImportHistoryItem(BaseModel):
    """Import history list item."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    imported_at: datetime
    source: str
    filename: Optional[str]
    date_from: Optional[date]
    date_to: Optional[date]
    raw_events: int
    trades_created: int
    trades_updated: int


# ============================================================================
# Analytics Schemas
# ============================================================================

class AnalyticsSummary(BaseModel):
    """Overall P&L summary."""
    total_trades: int
    closed_trades: int
    open_trades: int
    total_pnl_gross: Decimal
    total_pnl_net: Decimal
    total_fees: Decimal
    win_count: int
    loss_count: int
    win_rate: float
    avg_winner: Decimal
    avg_loser: Decimal


class StrategyBreakdown(BaseModel):
    """P&L by strategy type."""
    strategy: str
    trade_count: int
    win_count: int
    pnl_net: float
    total_fees: float


class UnderlyingBreakdown(BaseModel):
    """P&L by underlying symbol."""
    underlying: str
    trade_count: int
    win_count: int
    pnl_net: float
    total_fees: float


# ============================================================================
# User/Billing Schemas
# ============================================================================

class UserProfile(BaseModel):
    """User profile (what the user sees about themselves)."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    subscription_status: str
    subscription_tier: str


class BillingStatus(BaseModel):
    """Billing/subscription status."""
    subscription_status: str
    subscription_tier: str
    current_period_end: Optional[datetime]
