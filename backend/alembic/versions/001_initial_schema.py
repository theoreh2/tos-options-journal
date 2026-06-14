"""Initial schema with secure owner_key design.

Revision ID: 001_initial
Revises:
Create Date: 2025-06-13

Security architecture:
- profiles: Contains user identity + salt + computed data_key (SHA-256)
- billing: Separate table for Stripe data (isolated from trade data)
- trades/cash_events/trade_legs: Use owner_key (hash) instead of FK to users
  - If these tables leak, attacker cannot link back to users
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ========================================================================
    # profiles - User identity table (protected)
    # ========================================================================
    op.create_table(
        "profiles",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True,
                  comment="References auth.users(id) from Supabase"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("salt", sa.String(64), nullable=False,
                  comment="Random salt for hashing user ID"),
        sa.Column("data_key", sa.String(64), nullable=False,
                  comment="SHA-256(id + salt) - used as owner_key in trade tables"),
    )
    op.create_index("ix_profiles_data_key", "profiles", ["data_key"])

    # ========================================================================
    # billing - Stripe data (separate for security)
    # ========================================================================
    op.create_table(
        "billing",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("profiles.id", ondelete="CASCADE"),
                  unique=True, nullable=False),
        sa.Column("stripe_customer_id", sa.String(255)),
        sa.Column("subscription_status", sa.String(50), default="free",
                  comment="free, trialing, active, canceled, past_due"),
        sa.Column("subscription_tier", sa.String(50), default="free",
                  comment="free, pro"),
        sa.Column("current_period_end", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    # ========================================================================
    # imports - Import history (links to profiles for RLS)
    # ========================================================================
    op.create_table(
        "imports",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("source", sa.String(50), nullable=False,
                  comment="TOS, TASTYTRADE, IBKR"),
        sa.Column("filename", sa.String(255)),
        sa.Column("date_from", sa.Date),
        sa.Column("date_to", sa.Date),
        sa.Column("raw_events", sa.Integer, default=0),
        sa.Column("trades_created", sa.Integer, default=0),
        sa.Column("trades_updated", sa.Integer, default=0),
    )
    op.create_index("ix_imports_user_id", "imports", ["user_id"])

    # ========================================================================
    # trades - Main trade table (uses owner_key hash, NOT FK to users)
    # ========================================================================
    op.create_table(
        "trades",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("owner_key", sa.String(64), nullable=False,
                  comment="SHA-256 hash - NOT a FK, cannot be joined to users"),
        sa.Column("import_id", postgresql.UUID(as_uuid=False),
                  comment="Which import created this trade"),
        sa.Column("underlying", sa.String(20), nullable=False),
        sa.Column("strategy", sa.String(50), nullable=False,
                  comment="StrategyType enum value"),
        sa.Column("spread_label", sa.String(50),
                  comment="Raw TOS label"),
        sa.Column("open_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("close_time", sa.DateTime(timezone=True)),
        sa.Column("expiration", sa.Date),
        sa.Column("is_closed", sa.Boolean, default=False),
        sa.Column("is_expired", sa.Boolean, default=False),
        sa.Column("open_amount", sa.Numeric(12, 2), nullable=False,
                  comment="Net cash at open (+ = credit, - = debit)"),
        sa.Column("close_amount", sa.Numeric(12, 2), default=0),
        sa.Column("total_fees", sa.Numeric(12, 2), default=0),
        sa.Column("realized_pnl", sa.Numeric(12, 2), default=0,
                  comment="Gross P&L before fees"),
        sa.Column("realized_pnl_net", sa.Numeric(12, 2), default=0,
                  comment="Net P&L after fees"),
        sa.Column("dte_at_entry", sa.Integer),
        sa.Column("iv_rank_at_entry", sa.Numeric(5, 2)),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_index("ix_trades_owner_key", "trades", ["owner_key"])
    op.create_index("ix_trades_underlying", "trades", ["underlying"])
    op.create_index("ix_trades_dedup", "trades",
                    ["owner_key", "underlying", "open_time"], unique=True)

    # ========================================================================
    # cash_events - Cash flow events (uses owner_key hash)
    # ========================================================================
    op.create_table(
        "cash_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("trade_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("trades.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_key", sa.String(64), nullable=False,
                  comment="SHA-256 hash - NOT a FK"),
        sa.Column("ref", sa.String(50), comment="TOS REF# (order ID)"),
        sa.Column("event_date", sa.Date, nullable=False),
        sa.Column("event_time", sa.String(20)),
        sa.Column("event_type", sa.String(20), nullable=False,
                  comment="OPEN, CLOSE, EXPIRATION, ASSIGNMENT"),
        sa.Column("description", sa.Text),
        sa.Column("direction", sa.String(10), comment="BUY or SELL"),
        sa.Column("qty", sa.Integer, default=0),
        sa.Column("strategy_label", sa.String(50)),
        sa.Column("expiration", sa.Date),
        sa.Column("strikes", postgresql.ARRAY(sa.Numeric(12, 2)),
                  comment="Array of strike prices"),
        sa.Column("option_type", sa.String(10), comment="CALL or PUT"),
        sa.Column("net_price", sa.Numeric(12, 4)),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False,
                  comment="Net cash impact"),
        sa.Column("misc_fees", sa.Numeric(12, 2), default=0),
        sa.Column("commissions", sa.Numeric(12, 2), default=0),
    )
    op.create_index("ix_cash_events_owner_key", "cash_events", ["owner_key"])
    op.create_index("ix_cash_events_trade_id", "cash_events", ["trade_id"])

    # ========================================================================
    # trade_legs - Leg detail (uses owner_key hash)
    # ========================================================================
    op.create_table(
        "trade_legs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("trade_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("trades.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_key", sa.String(64), nullable=False,
                  comment="SHA-256 hash - NOT a FK"),
        sa.Column("side", sa.String(10), nullable=False, comment="BUY or SELL"),
        sa.Column("qty", sa.Integer, nullable=False),
        sa.Column("pos_effect", sa.String(20), comment="TO OPEN or TO CLOSE"),
        sa.Column("expiration", sa.Date),
        sa.Column("strike", sa.Numeric(12, 2)),
        sa.Column("option_type", sa.String(10), comment="CALL or PUT"),
        sa.Column("price", sa.Numeric(12, 4)),
    )
    op.create_index("ix_trade_legs_owner_key", "trade_legs", ["owner_key"])
    op.create_index("ix_trade_legs_trade_id", "trade_legs", ["trade_id"])


def downgrade() -> None:
    op.drop_table("trade_legs")
    op.drop_table("cash_events")
    op.drop_table("trades")
    op.drop_table("imports")
    op.drop_table("billing")
    op.drop_table("profiles")
