"""Check for RAD (expiration) events in the database."""

import sys
sys.path.insert(0, '/Users/theodorereh/Documents/git/claude/tos_options_journal/backend')

from sqlalchemy import select
from database import SessionLocal
from models.db import CashEvent

def check():
    db = SessionLocal()

    # Get all cash events
    all_events = db.execute(
        select(CashEvent).order_by(CashEvent.event_date)
    ).scalars().all()

    print(f"\nTotal cash events: {len(all_events)}")

    # Count by type
    by_type = {}
    for e in all_events:
        by_type[e.event_type] = by_type.get(e.event_type, 0) + 1

    print("\nBy event type:")
    for t, count in sorted(by_type.items()):
        print(f"  {t}: {count}")

    # Show RAD events
    rad_events = [e for e in all_events if e.event_type in ('EXPIRATION', 'ASSIGNMENT')]
    print(f"\n\nRAD Events (Expiration/Assignment): {len(rad_events)}")
    for e in rad_events[:20]:  # First 20
        print(f"  {e.event_date} {e.event_type}: {e.underlying} {e.strikes} {e.option_type}")
        print(f"    {e.description[:80]}...")

    db.close()

if __name__ == "__main__":
    check()
