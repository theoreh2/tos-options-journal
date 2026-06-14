"""Enable Row Level Security on all tables.

Revision ID: 002_rls
Revises: 001_initial
Create Date: 2025-06-13

RLS Policies:
- profiles: users can only read/write their own profile (id = auth.uid())
- billing: users can only read their own billing (user_id = auth.uid())
- imports: users can only read their own imports (user_id = auth.uid())
- trades/cash_events/trade_legs: Queries must filter by owner_key
  (app computes owner_key from JWT, no direct link to auth.uid in these tables)
"""

from typing import Sequence, Union

from alembic import op

revision: str = "002_rls"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable RLS on all tables
    op.execute("ALTER TABLE profiles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE billing ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE imports ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE trades ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE cash_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE trade_legs ENABLE ROW LEVEL SECURITY")

    # ========================================================================
    # profiles policies - direct auth.uid() check
    # ========================================================================
    op.execute("""
        CREATE POLICY profiles_select ON profiles
        FOR SELECT USING (id = auth.uid())
    """)
    op.execute("""
        CREATE POLICY profiles_insert ON profiles
        FOR INSERT WITH CHECK (id = auth.uid())
    """)
    op.execute("""
        CREATE POLICY profiles_update ON profiles
        FOR UPDATE USING (id = auth.uid())
    """)
    op.execute("""
        CREATE POLICY profiles_delete ON profiles
        FOR DELETE USING (id = auth.uid())
    """)

    # ========================================================================
    # billing policies - user_id FK check
    # ========================================================================
    op.execute("""
        CREATE POLICY billing_select ON billing
        FOR SELECT USING (user_id = auth.uid())
    """)
    op.execute("""
        CREATE POLICY billing_insert ON billing
        FOR INSERT WITH CHECK (user_id = auth.uid())
    """)
    op.execute("""
        CREATE POLICY billing_update ON billing
        FOR UPDATE USING (user_id = auth.uid())
    """)
    op.execute("""
        CREATE POLICY billing_delete ON billing
        FOR DELETE USING (user_id = auth.uid())
    """)

    # ========================================================================
    # imports policies - user_id FK check
    # ========================================================================
    op.execute("""
        CREATE POLICY imports_select ON imports
        FOR SELECT USING (user_id = auth.uid())
    """)
    op.execute("""
        CREATE POLICY imports_insert ON imports
        FOR INSERT WITH CHECK (user_id = auth.uid())
    """)
    op.execute("""
        CREATE POLICY imports_update ON imports
        FOR UPDATE USING (user_id = auth.uid())
    """)
    op.execute("""
        CREATE POLICY imports_delete ON imports
        FOR DELETE USING (user_id = auth.uid())
    """)

    # ========================================================================
    # trades policies - owner_key lookup via subquery
    # ========================================================================
    op.execute("""
        CREATE POLICY trades_select ON trades
        FOR SELECT USING (
            owner_key = (SELECT data_key FROM profiles WHERE id = auth.uid())
        )
    """)
    op.execute("""
        CREATE POLICY trades_insert ON trades
        FOR INSERT WITH CHECK (
            owner_key = (SELECT data_key FROM profiles WHERE id = auth.uid())
        )
    """)
    op.execute("""
        CREATE POLICY trades_update ON trades
        FOR UPDATE USING (
            owner_key = (SELECT data_key FROM profiles WHERE id = auth.uid())
        )
    """)
    op.execute("""
        CREATE POLICY trades_delete ON trades
        FOR DELETE USING (
            owner_key = (SELECT data_key FROM profiles WHERE id = auth.uid())
        )
    """)

    # ========================================================================
    # cash_events policies - owner_key lookup via subquery
    # ========================================================================
    op.execute("""
        CREATE POLICY cash_events_select ON cash_events
        FOR SELECT USING (
            owner_key = (SELECT data_key FROM profiles WHERE id = auth.uid())
        )
    """)
    op.execute("""
        CREATE POLICY cash_events_insert ON cash_events
        FOR INSERT WITH CHECK (
            owner_key = (SELECT data_key FROM profiles WHERE id = auth.uid())
        )
    """)
    op.execute("""
        CREATE POLICY cash_events_update ON cash_events
        FOR UPDATE USING (
            owner_key = (SELECT data_key FROM profiles WHERE id = auth.uid())
        )
    """)
    op.execute("""
        CREATE POLICY cash_events_delete ON cash_events
        FOR DELETE USING (
            owner_key = (SELECT data_key FROM profiles WHERE id = auth.uid())
        )
    """)

    # ========================================================================
    # trade_legs policies - owner_key lookup via subquery
    # ========================================================================
    op.execute("""
        CREATE POLICY trade_legs_select ON trade_legs
        FOR SELECT USING (
            owner_key = (SELECT data_key FROM profiles WHERE id = auth.uid())
        )
    """)
    op.execute("""
        CREATE POLICY trade_legs_insert ON trade_legs
        FOR INSERT WITH CHECK (
            owner_key = (SELECT data_key FROM profiles WHERE id = auth.uid())
        )
    """)
    op.execute("""
        CREATE POLICY trade_legs_update ON trade_legs
        FOR UPDATE USING (
            owner_key = (SELECT data_key FROM profiles WHERE id = auth.uid())
        )
    """)
    op.execute("""
        CREATE POLICY trade_legs_delete ON trade_legs
        FOR DELETE USING (
            owner_key = (SELECT data_key FROM profiles WHERE id = auth.uid())
        )
    """)


def downgrade() -> None:
    # Drop all policies
    for table in ["profiles", "billing", "imports", "trades", "cash_events", "trade_legs"]:
        for action in ["select", "insert", "update", "delete"]:
            op.execute(f"DROP POLICY IF EXISTS {table}_{action} ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
