"""Find potential close events that didn't match to open trades."""

import sys
sys.path.insert(0, '/Users/theodorereh/Documents/git/claude/tos_options_journal/backend')

from sqlalchemy import select
from database import SessionLocal
from models.db import Trade, CashEvent
from datetime import date

def analyze():
    db = SessionLocal()

    # Get all open trades with past expirations
    open_trades = db.execute(
        select(Trade).where(
            Trade.is_closed == False,
            Trade.expiration < date.today()
        ).order_by(Trade.underlying, Trade.open_time)
    ).scalars().all()

    print(f"\n{'='*80}")
    print(f"ANALYSIS: {len(open_trades)} trades with past expiration showing as open")
    print(f"{'='*80}\n")

    # Group by underlying
    by_underlying = {}
    for t in open_trades:
        if t.underlying not in by_underlying:
            by_underlying[t.underlying] = []
        by_underlying[t.underlying].append(t)

    # For each underlying, look for potential close events
    for underlying, trades in sorted(by_underlying.items()):
        print(f"\n{'='*60}")
        print(f"{underlying} - {len(trades)} open trade(s)")
        print(f"{'='*60}")

        # Get ALL cash events for this underlying
        all_events = db.execute(
            select(CashEvent)
            .join(Trade)
            .where(Trade.underlying == underlying)
            .order_by(CashEvent.event_date, CashEvent.event_time)
        ).scalars().all()

        # Show open trades and their events
        for t in trades:
            events = db.execute(
                select(CashEvent).where(CashEvent.trade_id == t.id)
            ).scalars().all()

            print(f"\n  TRADE: {t.strategy} exp={t.expiration} open=${t.open_amount}")
            print(f"    Open time: {t.open_time}")
            for e in events:
                print(f"    Event: {e.event_date} {e.event_type} {e.direction} {e.qty}x strikes={e.strikes}")

        # Show all close events for this underlying that might be orphaned
        close_events = [e for e in all_events if e.event_type == 'CLOSE']
        if close_events:
            print(f"\n  ALL CLOSE EVENTS for {underlying}:")
            for e in close_events:
                print(f"    {e.event_date} {e.direction} {e.qty}x strikes={e.strikes} ${e.amount}")

        # Check if any close events exist that could match
        for t in trades:
            t_events = [e for e in all_events if e.trade_id == t.id]
            t_open_event = [e for e in t_events if e.event_type == 'OPEN']
            if t_open_event:
                oe = t_open_event[0]
                # Look for matching close
                potential_closes = [
                    e for e in all_events
                    if e.event_type == 'CLOSE'
                    and set(e.strikes) & set(oe.strikes)  # overlapping strikes
                    and e.event_date >= oe.event_date
                ]
                if potential_closes:
                    print(f"\n  ⚠️  POTENTIAL MATCHES for trade opened {oe.event_date}:")
                    for pc in potential_closes:
                        print(f"      {pc.event_date} {pc.direction} strikes={pc.strikes} ${pc.amount}")

    db.close()

if __name__ == "__main__":
    analyze()
