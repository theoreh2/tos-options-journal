"""
TOS (thinkorswim / Charles Schwab) Account Statement CSV Parser - v3.1

PRIMARY:   Cash Balance section  — drives all events (TRD, RAD), P&L, fees
SECONDARY: Account Trade History — leg detail for strategy classification

Cash Balance description format:
  TRD: "SOLD -2 VERTICAL ADBE 100 (Weeklys) 22 MAY 26 262.5/265 CALL @.33 CBOE"
       "BOT +1 CRM 100 (Weeklys) 29 MAY 26 160 PUT @1.13 MIAX"
  RAD: "Removed due to Expiration CALL NVIDIA CORP $230 EXP 05/29/26: EXP: -1.0 .NVDA260529C230"

P&L per trade  = open_amount + close_amount  (gross, from AMOUNT column)
Fees per trade = sum of abs(misc) + abs(comm) across all rows for that trade
Net P&L        = gross P&L - total_fees

Key design decisions:
  - Open vs close determined by direction relative to existing open position:
      SOLD into existing short = adding (new open)
      BOT into existing short  = closing
      BOT into existing long   = adding (new open)
      SOLD into existing long  = closing
  - Same-REF duplicate rows (split fills) are accumulated, not double-counted
  - RAD rows matched to open trade by underlying + expiration + nearest strike
  - Unmatched closes (position opened before export window) flagged, not fabricated
"""

from __future__ import annotations

import csv
import io
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class PosEffect(str, Enum):
    OPEN = "TO OPEN"
    CLOSE = "TO CLOSE"

class OptionType(str, Enum):
    CALL = "CALL"
    PUT = "PUT"

class AssetType(str, Enum):
    OPTION = "OPTION"
    STOCK = "STOCK"
    FUTURE_OPTION = "FUTURE_OPTION"

class EventType(str, Enum):
    OPEN = "OPEN"
    CLOSE = "CLOSE"
    EXPIRATION = "EXPIRATION"
    ASSIGNMENT = "ASSIGNMENT"
    UNMATCHED_CLOSE = "UNMATCHED_CLOSE"   # position opened before export window

class StrategyType(str, Enum):
    SINGLE_CALL    = "SINGLE_CALL"
    SINGLE_PUT     = "SINGLE_PUT"
    VERTICAL_CALL  = "VERTICAL_CALL"
    VERTICAL_PUT   = "VERTICAL_PUT"
    BUTTERFLY_CALL = "BUTTERFLY_CALL"
    BUTTERFLY_PUT  = "BUTTERFLY_PUT"
    IRON_CONDOR    = "IRON_CONDOR"
    IRON_BUTTERFLY = "IRON_BUTTERFLY"
    STRADDLE       = "STRADDLE"
    STRANGLE       = "STRANGLE"
    CALENDAR       = "CALENDAR"
    DIAGONAL       = "DIAGONAL"
    COVERED_CALL   = "COVERED_CALL"
    STOCK          = "STOCK"
    UNKNOWN        = "UNKNOWN"


# ---------------------------------------------------------------------------
# Field parsers
# ---------------------------------------------------------------------------

_MONTH_MAP = {m: i+1 for i, m in enumerate(
    ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]
)}

def _parse_exp_words(val: str) -> Optional[date]:
    parts = val.strip().upper().split()
    if len(parts) == 3:
        try:
            return date(2000 + int(parts[2]), _MONTH_MAP[parts[1]], int(parts[0]))
        except (ValueError, KeyError):
            pass
    return None

def _parse_exp_slash(val: str) -> Optional[date]:
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(val.strip(), fmt).date()
        except ValueError:
            continue
    return None

def _parse_float(val: str) -> float:
    val = val.strip().replace("$", "").replace(",", "")
    if not val or val in ("--", "N/A"):
        return 0.0
    if val.startswith("(") and val.endswith(")"):
        return -float(val[1:-1])
    try:
        return float(val)
    except ValueError:
        return 0.0

def _parse_qty(val: str) -> int:
    try:
        return abs(int(float(val.strip().lstrip("+"))))
    except (ValueError, AttributeError):
        return 0


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CashEvent:
    ref: str
    date: Optional[date]
    time_str: str
    event_type: EventType
    description: str
    direction: Optional[Side]         = None
    qty: int                          = 0
    strategy_label: str               = ""
    underlying: str                   = ""
    expiration: Optional[date]        = None
    strikes: list[float]              = field(default_factory=list)
    option_type: Optional[OptionType] = None
    net_price: float                  = 0.0
    exchange: str                     = ""
    amount: float                     = 0.0
    misc_fees: float                  = 0.0
    commissions: float                = 0.0

    @property
    def total_fees(self) -> float:
        return abs(self.misc_fees) + abs(self.commissions)

    @property
    def exec_datetime(self) -> Optional[datetime]:
        if self.date and self.time_str:
            try:
                return datetime.combine(
                    self.date,
                    datetime.strptime(self.time_str, "%H:%M:%S").time()
                )
            except ValueError:
                pass
        return None

    @property
    def primary_strike(self) -> Optional[float]:
        return self.strikes[0] if self.strikes else None


@dataclass
class TradeLeg:
    ref: str = ""
    exec_time: Optional[datetime] = None
    spread_label: str = ""
    side: Optional[Side] = None
    qty: int = 0
    pos_effect: Optional[PosEffect] = None
    symbol: str = ""
    expiration: Optional[date] = None
    strike: Optional[float] = None
    option_type: Optional[OptionType] = None
    asset_type: AssetType = AssetType.OPTION
    price: float = 0.0

    @property
    def is_short(self) -> bool:
        return self.side == Side.SELL and self.pos_effect == PosEffect.OPEN


@dataclass
class Trade:
    id: str = field(default_factory=lambda: str(uuid4()))
    underlying: str = ""
    strategy: StrategyType = StrategyType.UNKNOWN
    spread_label: str = ""
    open_events: list[CashEvent] = field(default_factory=list)
    close_events: list[CashEvent] = field(default_factory=list)
    legs: list[TradeLeg] = field(default_factory=list)
    open_time: Optional[datetime] = None
    close_time: Optional[datetime] = None
    expiration: Optional[date] = None
    is_closed: bool = False
    is_expired: bool = False
    is_unmatched: bool = False   # close with no known open (pre-window)
    open_amount: float = 0.0
    close_amount: float = 0.0
    total_fees: float = 0.0
    realized_pnl: Optional[float] = None
    realized_pnl_net: Optional[float] = None
    notes: str = ""

    def recalculate(self) -> None:
        self.open_amount = sum(e.amount for e in self.open_events)
        self.close_amount = sum(e.amount for e in self.close_events)
        self.total_fees = sum(e.total_fees for e in self.open_events + self.close_events)
        if self.is_closed or self.is_expired:
            self.realized_pnl = round(self.open_amount + self.close_amount, 2)
            self.realized_pnl_net = round(self.realized_pnl - self.total_fees, 2)


# ---------------------------------------------------------------------------
# Description regex parsers
# ---------------------------------------------------------------------------

_TRD_RE = re.compile(
    r"^(?P<dir>SOLD|BOT)\s+"
    r"(?P<signed_qty>[+-]\d+)\s+"
    r"(?:(?P<strat>VERTICAL|BUTTERFLY|IRON\s+CONDOR|IRON\s+BUTTERFLY|"
    r"CALENDAR|DIAGONAL|STRANGLE|STRADDLE)\s+)?"
    r"(?P<sym>[A-Z]+)\s+"
    r"100\s+"
    r"(?:\(Weeklys\)\s+)?"
    r"(?P<exp>\d{1,2}\s+[A-Z]{3}\s+\d{2})\s+"
    r"(?P<strikes>[\d./]+)\s+"
    r"(?P<otype>CALL|PUT)\s+"
    r"@(?P<price>-?[\d.]+)",
    re.IGNORECASE,
)

_RAD_RE = re.compile(
    r"Removed due to (?P<reason>Expiration|Assignment)\s+"
    r"(?P<otype>CALL|PUT)\s+"
    r"(?P<name>.+?)\s+\$(?P<strike>[\d.]+)\s+"
    r"EXP\s+(?P<exp>[\d/]+):\s+EXP:\s+(?P<qty>-?[\d.]+)",
    re.IGNORECASE,
)

_RAD_SYM_RE = re.compile(r"\.?([A-Z]+)\d{6}[CP][\d.]+$")


def _parse_trd(desc: str) -> Optional[dict]:
    m = _TRD_RE.match(desc.strip())
    if not m:
        return None
    strikes = [float(s) for s in m.group("strikes").split("/") if s]
    strat = (m.group("strat") or "SINGLE").strip().upper().replace(" ", "_")
    return {
        "direction": Side.SELL if m.group("dir").upper() == "SOLD" else Side.BUY,
        "qty": abs(int(m.group("signed_qty"))),
        "strategy_label": strat,
        "underlying": m.group("sym").upper(),
        "expiration": _parse_exp_words(m.group("exp")),
        "strikes": strikes,
        "option_type": OptionType.CALL if m.group("otype").upper() == "CALL" else OptionType.PUT,
        "net_price": float(m.group("price")),
    }


def _parse_rad(desc: str) -> Optional[dict]:
    m = _RAD_RE.search(desc)
    if not m:
        return None
    sym_m = _RAD_SYM_RE.search(desc)
    return {
        "underlying": sym_m.group(1) if sym_m else "",
        "option_type": OptionType.CALL if m.group("otype").upper() == "CALL" else OptionType.PUT,
        "strike": float(m.group("strike")),
        "expiration": _parse_exp_slash(m.group("exp")),
        "qty": float(m.group("qty")),
        "event_type": EventType.EXPIRATION if m.group("reason").upper() == "EXPIRATION"
                      else EventType.ASSIGNMENT,
    }


# ---------------------------------------------------------------------------
# Position tracker
# ---------------------------------------------------------------------------

class PositionTracker:
    """
    Tracks open positions per underlying.
    Each position is a tuple: (direction: Side, strikes: set, expiration, option_type, trade)
    direction = SELL means net short (credit spread opened with SOLD)
                BUY  means net long (debit spread opened with BOT)
    """

    def __init__(self):
        # underlying -> list of open position dicts
        self._positions: dict[str, list[dict]] = {}

    def find_open(self, event: CashEvent) -> Optional[Trade]:
        """Find an open trade that this event would close."""
        for pos in self._positions.get(event.underlying, []):
            if not self._contracts_match(pos, event):
                continue
            # A close reverses the direction:
            # If open was SELL (short), close is BUY
            # If open was BUY (long), close is SELL
            open_dir = pos["direction"]
            if open_dir == Side.SELL and event.direction == Side.BUY:
                return pos["trade"]
            if open_dir == Side.BUY and event.direction == Side.SELL:
                return pos["trade"]
        return None

    def add_open(self, event: CashEvent, trade: Trade) -> None:
        if event.underlying not in self._positions:
            self._positions[event.underlying] = []
        self._positions[event.underlying].append({
            "direction": event.direction,
            "strikes": set(event.strikes),
            "expiration": event.expiration,
            "option_type": event.option_type,
            "trade": trade,
        })

    def remove(self, trade: Trade) -> None:
        for sym, positions in self._positions.items():
            self._positions[sym] = [p for p in positions if p["trade"] is not trade]

    def find_for_expiration(self, event: CashEvent) -> Optional[Trade]:
        """Match RAD event to open trade. Strike nearest match within open strikes."""
        for pos in self._positions.get(event.underlying, []):
            if pos["expiration"] != event.expiration:
                continue
            if pos["option_type"] != event.option_type:
                continue
            # Any of the event's strikes overlap with open strikes
            if event.strikes and pos["strikes"] & set(event.strikes):
                return pos["trade"]
            # Fallback: strike within $0.01
            if event.strikes:
                for open_strike in pos["strikes"]:
                    if abs(open_strike - event.strikes[0]) < 0.01:
                        return pos["trade"]
        return None

    def _contracts_match(self, pos: dict, event: CashEvent) -> bool:
        if pos["expiration"] != event.expiration:
            return False
        if pos["option_type"] != event.option_type:
            return False
        # At least one strike in common
        return bool(pos["strikes"] & set(event.strikes))

    def open_trades(self) -> list[Trade]:
        seen = set()
        result = []
        for positions in self._positions.values():
            for p in positions:
                t = p["trade"]
                if id(t) not in seen:
                    seen.add(id(t))
                    result.append(t)
        return result


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

class TOSParseError(Exception):
    pass


_SIDE_MAP = {"BUY": Side.BUY, "BOT": Side.BUY, "SELL": Side.SELL, "SLD": Side.SELL}
_POS_MAP = {
    "TO OPEN": PosEffect.OPEN, "OPEN": PosEffect.OPEN,
    "TO CLOSE": PosEffect.CLOSE, "CLOSE": PosEffect.CLOSE,
}


class TOSParser:

    def parse(self, content: str | bytes) -> "ParseResult":
        if isinstance(content, bytes):
            content = content.decode("utf-8-sig", errors="replace")

        cash_events = self._parse_cash_balance(content)
        history_legs = self._parse_trade_history(content)

        if not cash_events:
            raise TOSParseError(
                "No trade events found in Cash Balance section. "
                "Export from Monitor > Account Statement."
            )

        trades = self._build_trades(cash_events, history_legs)
        return ParseResult(cash_events=cash_events, trades=trades)

    # ------------------------------------------------------------------
    # 1. Parse Cash Balance
    # ------------------------------------------------------------------

    def _parse_cash_balance(self, content: str) -> list[CashEvent]:
        lines = content.splitlines()
        events: list[CashEvent] = []
        seen_refs: set[str] = set()   # deduplicate same-REF split fills by accumulating
        ref_accum: dict[str, CashEvent] = {}
        in_section = False

        for line in lines:
            if line.strip().lower() == "cash balance":
                in_section = True
                continue
            if not in_section:
                continue
            if not line.strip():
                break

            row = next(csv.reader([line]))
            if len(row) < 3:
                continue
            type_ = row[2].strip()
            if type_ not in ("TRD", "RAD"):
                continue

            date_str = row[0].strip() if row else ""
            time_str = row[1].strip() if len(row) > 1 else ""
            ref = row[3].strip().strip('="').rstrip('"') if len(row) > 3 else ""
            desc = row[4].strip() if len(row) > 4 else ""
            misc = _parse_float(row[5]) if len(row) > 5 else 0.0
            comm = _parse_float(row[6]) if len(row) > 6 else 0.0
            amt  = _parse_float(row[7]) if len(row) > 7 else 0.0

            parsed_date = None
            for fmt in ("%m/%d/%y", "%m/%d/%Y"):
                try:
                    parsed_date = datetime.strptime(date_str, fmt).date()
                    break
                except ValueError:
                    pass

            if type_ == "TRD":
                parsed = _parse_trd(desc)
                if not parsed:
                    logger.warning("Could not parse TRD description: %s", desc)
                    continue

                # Deduplicate split fills: same REF = same order, accumulate amounts/fees
                if ref in ref_accum:
                    existing = ref_accum[ref]
                    existing.amount += amt
                    existing.misc_fees += misc
                    existing.commissions += comm
                    existing.qty += parsed["qty"]
                    continue

                event = CashEvent(
                    ref=ref, date=parsed_date, time_str=time_str,
                    event_type=EventType.OPEN,  # resolved during build
                    description=desc,
                    direction=parsed["direction"],
                    qty=parsed["qty"],
                    strategy_label=parsed["strategy_label"],
                    underlying=parsed["underlying"],
                    expiration=parsed["expiration"],
                    strikes=parsed["strikes"],
                    option_type=parsed["option_type"],
                    net_price=parsed["net_price"],
                    amount=amt, misc_fees=misc, commissions=comm,
                )
                ref_accum[ref] = event
                events.append(event)

            else:  # RAD
                parsed = _parse_rad(desc)
                if not parsed:
                    logger.warning("Could not parse RAD description: %s", desc)
                    continue
                # RAD rows: one per leg of a multi-leg expiration
                # Group by (underlying, expiration, event_type) — same expiration event
                event = CashEvent(
                    ref=ref, date=parsed_date, time_str=time_str,
                    event_type=parsed["event_type"],
                    description=desc,
                    underlying=parsed["underlying"],
                    option_type=parsed["option_type"],
                    strikes=[parsed["strike"]],
                    expiration=parsed["expiration"],
                    qty=abs(int(parsed["qty"])),
                    amount=0.0, misc_fees=0.0, commissions=0.0,
                )
                events.append(event)

        logger.info("Parsed %d cash events", len(events))
        return events

    # ------------------------------------------------------------------
    # 2. Parse Account Trade History
    # ------------------------------------------------------------------

    def _parse_trade_history(self, content: str) -> dict[str, list[TradeLeg]]:
        lines = content.splitlines()
        block: list[str] = []
        in_section = False

        for line in lines:
            s = line.strip().strip('"').lower()
            if s in ("account trade history", "trades"):
                in_section = True
                continue
            if in_section:
                if not line.strip():
                    if block:
                        break
                    continue
                block.append(line)

        if not block:
            return {}
        return self._parse_history_block(block)

    def _parse_history_block(self, lines: list[str]) -> dict[str, list[TradeLeg]]:
        reader = csv.reader(io.StringIO("\n".join(lines)))
        raw_header = next(reader, None)
        if not raw_header:
            return {}

        headers = [h.strip().upper().replace(" ", "_") for h in raw_header]
        col = {h: i for i, h in enumerate(headers)}

        def g(row, name, default=""):
            i = col.get(name)
            return row[i].strip() if i is not None and i < len(row) else default

        result: dict[str, list[TradeLeg]] = {}
        current_time: Optional[datetime] = None
        current_spread: str = ""
        current_ref: str = ""
        skip = False

        for row in reader:
            if not any(c.strip() for c in row):
                continue

            exec_time_str = g(row, "EXEC_TIME")
            spread_str = g(row, "SPREAD")
            is_anchor = bool(exec_time_str) and bool(spread_str) and not spread_str.startswith("RE #")

            if is_anchor:
                if g(row, "ORDER_TYPE").upper() == "CANCELED":
                    skip = True
                    continue
                skip = False
                for fmt in ("%m/%d/%y %H:%M:%S", "%m/%d/%Y %H:%M:%S"):
                    try:
                        current_time = datetime.strptime(exec_time_str, fmt)
                        break
                    except ValueError:
                        pass
                current_spread = spread_str.strip()
                sym = g(row, "SYMBOL")
                current_ref = f"{exec_time_str.strip()}|{sym}"
            else:
                if skip or not current_time:
                    continue

            side = _SIDE_MAP.get(g(row, "SIDE").upper())
            pos = _POS_MAP.get(g(row, "POS_EFFECT").upper())
            symbol = g(row, "SYMBOL")
            if not side or not pos or not symbol:
                continue

            type_str = g(row, "TYPE").upper()
            option_type = None
            asset_type = AssetType.OPTION
            if type_str == "CALL":
                option_type = OptionType.CALL
            elif type_str == "PUT":
                option_type = OptionType.PUT
            else:
                asset_type = AssetType.STOCK

            exp_str = g(row, "EXP")
            expiration = _parse_exp_words(exp_str) or _parse_exp_slash(exp_str) if exp_str else None

            strike_str = g(row, "STRIKE")
            leg = TradeLeg(
                ref=current_ref,
                exec_time=current_time,
                spread_label=current_spread,
                side=side,
                qty=_parse_qty(g(row, "QTY")),
                pos_effect=pos,
                symbol=symbol,
                expiration=expiration,
                strike=float(strike_str) if strike_str else None,
                option_type=option_type,
                asset_type=asset_type,
                price=_parse_float(g(row, "PRICE")),
            )
            if current_ref not in result:
                result[current_ref] = []
            result[current_ref].append(leg)

        logger.info("Account Trade History: %d orders parsed", len(result))
        return result

    # ------------------------------------------------------------------
    # 3. Build trades
    # ------------------------------------------------------------------

    def _build_trades(
        self,
        events: list[CashEvent],
        history: dict[str, list[TradeLeg]],
    ) -> list[Trade]:

        tracker = PositionTracker()
        all_trades: list[Trade] = []

        for event in events:
            if not event.underlying:
                continue

            # ── RAD: expiration or assignment ──────────────────────────
            if event.event_type in (EventType.EXPIRATION, EventType.ASSIGNMENT):
                trade = tracker.find_for_expiration(event)
                if trade:
                    trade.close_events.append(event)
                    # Only mark closed once all legs accounted for
                    # (multi-leg expirations have one RAD per leg)
                    # We close after first match and trust recalculate()
                    if not trade.is_closed:
                        trade.is_expired = (event.event_type == EventType.EXPIRATION)
                        trade.is_closed = True
                        trade.close_time = event.exec_datetime
                        tracker.remove(trade)
                    trade.recalculate()
                else:
                    logger.warning(
                        "RAD %s %s %s — no open trade found (opened before export window)",
                        event.underlying, event.option_type, event.strikes
                    )
                continue

            # ── TRD: open or close ─────────────────────────────────────
            open_trade = tracker.find_open(event)

            if open_trade:
                # This event closes the open trade
                event.event_type = EventType.CLOSE
                open_trade.close_events.append(event)
                open_trade.close_time = event.exec_datetime
                open_trade.is_closed = True
                open_trade.recalculate()
                tracker.remove(open_trade)
            else:
                # New open position
                event.event_type = EventType.OPEN
                trade = Trade(
                    underlying=event.underlying,
                    spread_label=event.strategy_label,
                    expiration=event.expiration,
                    open_time=event.exec_datetime,
                )
                trade.open_events.append(event)
                trade.recalculate()
                tracker.add_open(event, trade)
                all_trades.append(trade)

        # Attach legs + classify
        self._attach_legs(all_trades, history)
        for trade in all_trades:
            trade.strategy = _classify_strategy(trade)

        return all_trades

    def _attach_legs(self, trades: list[Trade], history: dict[str, list[TradeLeg]]) -> None:
        """Match history legs to trades by exec_time + underlying."""
        time_sym_map: dict[tuple, list[TradeLeg]] = {}
        for ref, legs in history.items():
            if not legs or not legs[0].exec_time:
                continue
            t = legs[0].exec_time
            sym = legs[0].symbol
            key = (t.date(), t.time(), sym)
            time_sym_map[key] = legs

        for trade in trades:
            if not trade.open_time:
                continue
            key = (trade.open_time.date(), trade.open_time.time(), trade.underlying)
            legs = time_sym_map.get(key, [])
            trade.legs = [l for l in legs if l.pos_effect == PosEffect.OPEN]


# ---------------------------------------------------------------------------
# Strategy classifier  (driven by cash event spread_label)
# ---------------------------------------------------------------------------

def _classify_strategy(trade: Trade) -> StrategyType:
    label = trade.spread_label.upper().replace(" ", "_")
    ev = trade.open_events[0] if trade.open_events else None
    otype = ev.option_type if ev else None

    _MAP = {
        "SINGLE":          {OptionType.CALL: StrategyType.SINGLE_CALL,
                            OptionType.PUT:  StrategyType.SINGLE_PUT},
        "VERTICAL":        {OptionType.CALL: StrategyType.VERTICAL_CALL,
                            OptionType.PUT:  StrategyType.VERTICAL_PUT},
        "BUTTERFLY":       {OptionType.CALL: StrategyType.BUTTERFLY_CALL,
                            OptionType.PUT:  StrategyType.BUTTERFLY_PUT},
        "IRON_CONDOR":     {None: StrategyType.IRON_CONDOR},
        "IRON_BUTTERFLY":  {None: StrategyType.IRON_BUTTERFLY},
        "STRADDLE":        {None: StrategyType.STRADDLE},
        "STRANGLE":        {None: StrategyType.STRANGLE},
        "CALENDAR":        {None: StrategyType.CALENDAR},
        "DIAGONAL":        {None: StrategyType.DIAGONAL},
    }
    bucket = _MAP.get(label, {})
    return bucket.get(otype) or bucket.get(None) or StrategyType.UNKNOWN


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class ParseResult:
    cash_events: list[CashEvent]
    trades: list[Trade]
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        closed  = [t for t in self.trades if t.is_closed]
        open_   = [t for t in self.trades if not t.is_closed]
        expired = [t for t in self.trades if t.is_expired]

        strat_counts: dict[str, int] = {}
        for t in self.trades:
            strat_counts[t.strategy.value] = strat_counts.get(t.strategy.value, 0) + 1

        lines = [
            f"Cash events parsed: {len(self.cash_events)}",
            f"Trades total:       {len(self.trades)}",
            f"  Open:             {len(open_)}",
            f"  Closed:           {len(closed)}",
            f"    of which expired: {len(expired)}",
            f"Strategy breakdown:",
        ]
        for s, c in sorted(strat_counts.items(), key=lambda x: -x[1]):
            lines.append(f"  {s:<25} {c}")

        total_gross   = sum(t.realized_pnl or 0 for t in closed)
        total_fees    = sum(t.total_fees for t in self.trades)
        total_net     = sum(t.realized_pnl_net or 0 for t in closed)

        lines += [
            f"\nRealized P&L gross:          ${total_gross:,.2f}",
            f"Total fees (all trades):     ${total_fees:,.2f}",
            f"Realized P&L net of fees:    ${total_net:,.2f}",
        ]
        return "\n".join(lines)

    def to_dicts(self) -> list[dict]:
        rows = []
        for t in self.trades:
            rows.append({
                "id":                t.id,
                "underlying":        t.underlying,
                "strategy":          t.strategy.value,
                "spread_label":      t.spread_label,
                "open_time":         t.open_time.isoformat() if t.open_time else None,
                "close_time":        t.close_time.isoformat() if t.close_time else None,
                "expiration":        t.expiration.isoformat() if t.expiration else None,
                "is_closed":         t.is_closed,
                "is_expired":        t.is_expired,
                "open_amount":       round(t.open_amount, 2),
                "close_amount":      round(t.close_amount, 2),
                "total_fees":        round(t.total_fees, 2),
                "realized_pnl":      round(t.realized_pnl, 2) if t.realized_pnl is not None else None,
                "realized_pnl_net":  round(t.realized_pnl_net, 2) if t.realized_pnl_net is not None else None,
                "leg_count":         len(t.legs) or len(t.open_events),
                "notes":             t.notes,
            })
        return rows
