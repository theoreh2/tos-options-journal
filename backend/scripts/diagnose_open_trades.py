"""Diagnose why trades are showing as open when they should be closed."""

import sys
sys.path.insert(0, '/Users/theodorereh/Documents/git/claude/tos_options_journal/backend')

from sqlalchemy import select
from database import SessionLocal
from models.db import Trade, CashEvent

def diagnose():
    db = SessionLocal()

    # Get all open trades
    open_trades = db.execute(
        select(Trade).where(Trade.is_closed == False).order_by(Trade.open_time)
    ).scalars().all()

    print(f"\n{'='*80}")
    print(f"OPEN TRADES DIAGNOSIS - {len(open_trades)} trades showing as open")
    print(f"{'='*80}\n")

    for trade in open_trades:
        print(f"\n--- {trade.underlying} ---")
        print(f"  ID: {trade.id}")
        print(f"  Strategy: {trade.strategy}")
        print(f"  Open Time: {trade.open_time}")
        print(f"  Expiration: {trade.expiration}")
        print(f"  Open Amount: ${trade.open_amount}")
        print(f"  Close Amount: ${trade.close_amount}")
        print(f"  is_closed: {trade.is_closed}")
        print(f"  is_expired: {trade.is_expired}")

        # Get cash events for this trade
        events = db.execute(
            select(CashEvent).where(CashEvent.trade_id == trade.id).order_by(CashEvent.event_date)
        ).scalars().all()

        print(f"  Cash Events ({len(events)}):")
        for e in events:
            print(f"    - {e.event_date} {e.event_type}: {e.direction} {e.qty}x {e.strikes} {e.option_type} | ${e.amount}")
            print(f"      Desc: {e.description[:80]}..." if e.description and len(e.description) > 80 else f"      Desc: {e.description}")

        # Check if expiration has passed
        from datetime import date
        if trade.expiration and trade.expiration < date.today():
            print(f"  ⚠️  EXPIRATION HAS PASSED ({trade.expiration}) - should be closed!")

    db.close()

if __name__ == "__main__":
    diagnose()
