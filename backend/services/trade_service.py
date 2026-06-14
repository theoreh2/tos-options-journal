"""Trade service - handles import, upsert, and query logic."""

from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from models.db import Trade, CashEvent, TradeLeg, Profile, Import
from parser.tos_parser import TOSParser, ParseResult, Trade as ParsedTrade, CashEvent as ParsedCashEvent


class TradeService:
    """Service for managing trades."""

    def __init__(self, db: Session):
        self.db = db

    def get_user_data_key(self, user_id: str) -> str:
        """Get the data_key for a user (for querying trades)."""
        profile = self.db.execute(
            select(Profile.data_key).where(Profile.id == user_id)
        ).scalar_one_or_none()

        if not profile:
            raise ValueError(f"Profile not found for user {user_id}")

        return profile

    def import_tos_csv(
        self,
        user_id: str,
        content: str,
        filename: Optional[str] = None
    ) -> dict:
        """
        Import a TOS CSV file for a user.

        Returns:
            dict with import_id, trades_created, trades_updated, warnings
        """
        # Get user's data_key
        data_key = self.get_user_data_key(user_id)

        # Parse the CSV
        parser = TOSParser()
        result = parser.parse(content)

        # Determine date range from cash events
        date_from = None
        date_to = None
        if result.cash_events:
            dates = [e.date for e in result.cash_events if e.date]
            if dates:
                date_from = min(dates)
                date_to = max(dates)

        # Create import record
        import_record = Import(
            id=str(uuid4()),
            user_id=user_id,
            source="TOS",
            filename=filename,
            date_from=date_from,
            date_to=date_to,
            raw_events=len(result.cash_events),
        )
        self.db.add(import_record)

        # Upsert trades
        trades_created = 0
        trades_updated = 0
        warnings = list(result.errors) if result.errors else []

        for parsed_trade in result.trades:
            created = self._upsert_trade(data_key, import_record.id, parsed_trade)
            if created:
                trades_created += 1
            else:
                trades_updated += 1

        # Update import record
        import_record.trades_created = trades_created
        import_record.trades_updated = trades_updated

        self.db.commit()

        return {
            "import_id": import_record.id,
            "source": "TOS",
            "filename": filename,
            "date_from": date_from,
            "date_to": date_to,
            "raw_events": len(result.cash_events),
            "trades_created": trades_created,
            "trades_updated": trades_updated,
            "warnings": warnings,
        }

    def _upsert_trade(
        self,
        owner_key: str,
        import_id: str,
        parsed: ParsedTrade
    ) -> bool:
        """
        Upsert a trade. Returns True if created, False if updated.

        Dedup key: owner_key + underlying + open_time
        """
        open_time = parsed.open_time
        if not open_time:
            return False

        # Check if trade exists
        existing = self.db.execute(
            select(Trade).where(
                Trade.owner_key == owner_key,
                Trade.underlying == parsed.underlying,
                Trade.open_time == open_time,
            )
        ).scalar_one_or_none()

        if existing:
            # Update existing trade
            existing.close_time = parsed.close_time
            existing.is_closed = parsed.is_closed
            existing.is_expired = parsed.is_expired
            existing.close_amount = Decimal(str(parsed.close_amount))
            existing.total_fees = Decimal(str(parsed.total_fees))
            existing.realized_pnl = Decimal(str(parsed.realized_pnl)) if parsed.realized_pnl is not None else Decimal("0")
            existing.realized_pnl_net = Decimal(str(parsed.realized_pnl_net)) if parsed.realized_pnl_net is not None else Decimal("0")

            # Update cash events (delete and re-add)
            self.db.execute(
                CashEvent.__table__.delete().where(CashEvent.trade_id == existing.id)
            )
            self._add_cash_events(existing.id, owner_key, parsed)

            return False
        else:
            # Create new trade
            trade = Trade(
                id=str(uuid4()),
                owner_key=owner_key,
                import_id=import_id,
                underlying=parsed.underlying,
                strategy=parsed.strategy.value,
                spread_label=parsed.spread_label,
                open_time=open_time,
                close_time=parsed.close_time,
                expiration=parsed.expiration,
                is_closed=parsed.is_closed,
                is_expired=parsed.is_expired,
                open_amount=Decimal(str(parsed.open_amount)),
                close_amount=Decimal(str(parsed.close_amount)),
                total_fees=Decimal(str(parsed.total_fees)),
                realized_pnl=Decimal(str(parsed.realized_pnl)) if parsed.realized_pnl is not None else Decimal("0"),
                realized_pnl_net=Decimal(str(parsed.realized_pnl_net)) if parsed.realized_pnl_net is not None else Decimal("0"),
                dte_at_entry=self._calculate_dte(open_time.date(), parsed.expiration),
            )
            self.db.add(trade)
            self._add_cash_events(trade.id, owner_key, parsed)

            return True

    def _add_cash_events(
        self,
        trade_id: str,
        owner_key: str,
        parsed: ParsedTrade
    ) -> None:
        """Add cash events for a trade."""
        all_events = parsed.open_events + parsed.close_events

        for event in all_events:
            # Convert strikes from float to Decimal
            strikes = [Decimal(str(s)) for s in event.strikes] if event.strikes else []

            cash_event = CashEvent(
                id=str(uuid4()),
                trade_id=trade_id,
                owner_key=owner_key,
                ref=event.ref,
                event_date=event.date,
                event_time=event.time_str,
                event_type=event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type),
                description=event.description,
                direction=event.direction.value if event.direction and hasattr(event.direction, 'value') else str(event.direction) if event.direction else None,
                qty=event.qty,
                strategy_label=event.strategy_label,
                expiration=event.expiration,
                strikes=strikes,
                option_type=event.option_type.value if event.option_type and hasattr(event.option_type, 'value') else str(event.option_type) if event.option_type else None,
                net_price=Decimal(str(event.net_price)) if event.net_price else None,
                amount=Decimal(str(event.amount)),
                misc_fees=Decimal(str(event.misc_fees)),
                commissions=Decimal(str(event.commissions)),
            )
            self.db.add(cash_event)

    def _calculate_dte(self, open_date: date, expiration: Optional[date]) -> Optional[int]:
        """Calculate days to expiration at entry."""
        if not expiration:
            return None
        return (expiration - open_date).days

    def list_trades(
        self,
        owner_key: str,
        underlying: Optional[str] = None,
        strategy: Optional[str] = None,
        is_closed: Optional[bool] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        """List trades with filters."""
        query = select(Trade).where(Trade.owner_key == owner_key)

        if underlying:
            query = query.where(Trade.underlying == underlying)
        if strategy:
            query = query.where(Trade.strategy == strategy)
        if is_closed is not None:
            query = query.where(Trade.is_closed == is_closed)
        if date_from:
            query = query.where(func.date(Trade.open_time) >= date_from)
        if date_to:
            query = query.where(func.date(Trade.open_time) <= date_to)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total = self.db.execute(count_query).scalar() or 0

        # Paginate
        query = query.order_by(Trade.open_time.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        trades = self.db.execute(query).scalars().all()

        return {
            "trades": trades,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_trade(self, owner_key: str, trade_id: str) -> Optional[Trade]:
        """Get a single trade with cash events and legs."""
        return self.db.execute(
            select(Trade).where(
                Trade.owner_key == owner_key,
                Trade.id == trade_id,
            )
        ).scalar_one_or_none()

    def get_trade_detail(self, owner_key: str, trade_id: str) -> Optional[dict]:
        """Get a single trade with cash events and legs as dict."""
        trade = self.db.execute(
            select(Trade).where(
                Trade.owner_key == owner_key,
                Trade.id == trade_id,
            )
        ).scalar_one_or_none()

        if not trade:
            return None

        # Get cash events
        cash_events = self.db.execute(
            select(CashEvent).where(CashEvent.trade_id == trade_id)
        ).scalars().all()

        # Get legs
        legs = self.db.execute(
            select(TradeLeg).where(TradeLeg.trade_id == trade_id)
        ).scalars().all()

        return {
            "id": trade.id,
            "underlying": trade.underlying,
            "strategy": trade.strategy,
            "spread_label": trade.spread_label,
            "open_time": trade.open_time.isoformat() if trade.open_time else None,
            "close_time": trade.close_time.isoformat() if trade.close_time else None,
            "expiration": trade.expiration.isoformat() if trade.expiration else None,
            "is_closed": trade.is_closed,
            "is_expired": trade.is_expired,
            "open_amount": float(trade.open_amount),
            "close_amount": float(trade.close_amount),
            "total_fees": float(trade.total_fees),
            "realized_pnl": float(trade.realized_pnl),
            "realized_pnl_net": float(trade.realized_pnl_net),
            "dte_at_entry": trade.dte_at_entry,
            "notes": trade.notes or "",
            "cash_events": [
                {
                    "id": e.id,
                    "event_type": e.event_type,
                    "event_date": e.event_date.isoformat() if e.event_date else None,
                    "direction": e.direction,
                    "qty": e.qty,
                    "strikes": [float(s) for s in e.strikes] if e.strikes else [],
                    "option_type": e.option_type,
                    "amount": float(e.amount),
                    "misc_fees": float(e.misc_fees),
                    "commissions": float(e.commissions),
                    "description": e.description,
                }
                for e in cash_events
            ],
            "legs": [
                {
                    "id": l.id,
                    "side": l.side,
                    "qty": l.qty,
                    "strike": float(l.strike) if l.strike else None,
                    "option_type": l.option_type,
                    "expiration": l.expiration.isoformat() if l.expiration else None,
                    "price": float(l.price) if l.price else None,
                }
                for l in legs
            ],
        }

    def update_trade_notes(self, owner_key: str, trade_id: str, notes: str) -> bool:
        """Update notes for a trade."""
        trade = self.db.execute(
            select(Trade).where(
                Trade.owner_key == owner_key,
                Trade.id == trade_id,
            )
        ).scalar_one_or_none()

        if not trade:
            return False

        trade.notes = notes
        self.db.commit()
        return True

    def get_unique_strategies(self, owner_key: str) -> list[str]:
        """Get list of unique strategies used."""
        result = self.db.execute(
            select(Trade.strategy).where(Trade.owner_key == owner_key).distinct()
        ).scalars().all()
        return sorted(result)

    def get_analytics_summary(self, owner_key: str) -> dict:
        """Get P&L summary analytics."""
        trades = self.db.execute(
            select(Trade).where(Trade.owner_key == owner_key)
        ).scalars().all()

        closed = [t for t in trades if t.is_closed]
        winners = [t for t in closed if t.realized_pnl_net > 0]
        losers = [t for t in closed if t.realized_pnl_net < 0]

        return {
            "total_trades": len(trades),
            "closed_trades": len(closed),
            "open_trades": len(trades) - len(closed),
            "total_pnl_gross": sum((t.realized_pnl for t in closed), Decimal("0")),
            "total_pnl_net": sum((t.realized_pnl_net for t in closed), Decimal("0")),
            "total_fees": sum((t.total_fees for t in trades), Decimal("0")),
            "win_count": len(winners),
            "loss_count": len(losers),
            "win_rate": len(winners) / len(closed) if closed else 0,
            "avg_winner": sum((t.realized_pnl_net for t in winners), Decimal("0")) / len(winners) if winners else Decimal("0"),
            "avg_loser": sum((t.realized_pnl_net for t in losers), Decimal("0")) / len(losers) if losers else Decimal("0"),
        }

    def get_analytics_by_strategy(self, owner_key: str) -> list[dict]:
        """Get P&L breakdown by strategy."""
        trades = self.db.execute(
            select(Trade).where(Trade.owner_key == owner_key, Trade.is_closed == True)
        ).scalars().all()

        # Group by strategy
        by_strategy: dict[str, list[Trade]] = {}
        for t in trades:
            if t.strategy not in by_strategy:
                by_strategy[t.strategy] = []
            by_strategy[t.strategy].append(t)

        results = []
        for strategy, strat_trades in by_strategy.items():
            winners = [t for t in strat_trades if t.realized_pnl_net > 0]
            pnl_net = sum((t.realized_pnl_net for t in strat_trades), Decimal("0"))
            results.append({
                "strategy": strategy,
                "trade_count": len(strat_trades),
                "win_count": len(winners),
                "pnl_net": float(pnl_net),
                "total_fees": float(sum((t.total_fees for t in strat_trades), Decimal("0"))),
            })

        # Sort by P&L descending
        results.sort(key=lambda x: x["pnl_net"], reverse=True)
        return results

    def get_analytics_by_underlying(self, owner_key: str) -> list[dict]:
        """Get P&L breakdown by underlying symbol."""
        trades = self.db.execute(
            select(Trade).where(Trade.owner_key == owner_key, Trade.is_closed == True)
        ).scalars().all()

        # Group by underlying
        by_underlying: dict[str, list[Trade]] = {}
        for t in trades:
            if t.underlying not in by_underlying:
                by_underlying[t.underlying] = []
            by_underlying[t.underlying].append(t)

        results = []
        for underlying, und_trades in by_underlying.items():
            winners = [t for t in und_trades if t.realized_pnl_net > 0]
            pnl_net = sum((t.realized_pnl_net for t in und_trades), Decimal("0"))
            results.append({
                "underlying": underlying,
                "trade_count": len(und_trades),
                "win_count": len(winners),
                "pnl_net": float(pnl_net),
                "total_fees": float(sum((t.total_fees for t in und_trades), Decimal("0"))),
            })

        # Sort by P&L descending
        results.sort(key=lambda x: x["pnl_net"], reverse=True)
        return results

    def get_pnl_over_time(self, owner_key: str) -> list[dict]:
        """Get cumulative P&L over time (by close date)."""
        trades = self.db.execute(
            select(Trade).where(
                Trade.owner_key == owner_key,
                Trade.is_closed == True,
                Trade.close_time.isnot(None)
            ).order_by(Trade.close_time)
        ).scalars().all()

        results = []
        cumulative = Decimal("0")
        for t in trades:
            cumulative += t.realized_pnl_net
            results.append({
                "date": t.close_time.date().isoformat() if t.close_time else None,
                "pnl": float(t.realized_pnl_net),
                "cumulative_pnl": float(cumulative),
                "underlying": t.underlying,
            })

        return results
