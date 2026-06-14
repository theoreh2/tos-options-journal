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
    STOCK_DELIVERY = "STOCK_DELIVERY"     # stock received/delivered from assignment
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

# DIAGONAL/CALENDAR with two expirations (roll): "21 JAN 28/24 APR 26"
_TRD_ROLL_RE = re.compile(
    r"^(?P<dir>SOLD|BOT)\s+"
    r"(?P<signed_qty>[+-]\d+)\s+"
    r"(?P<strat>CALENDAR|DIAGONAL)\s+"
    r"(?P<sym>[A-Z]+)\s+"
    r"100\s+"
    r"(?:\(Weeklys\)\s+)?"
    r"(?P<exp_far>\d{1,2}\s+[A-Z]{3}\s+\d{2})/"
    r"(?P<exp_near>\d{1,2}\s+[A-Z]{3}\s+\d{2})\s+"
    r"(?P<strikes>[\d./]+)\s+"
    r"(?P<otype>CALL|PUT)\s+"
    r"@(?P<price>-?[\d.]+)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Order confirmation format parser (for quick-add)
# ---------------------------------------------------------------------------
# Examples:
#   "BUY +2 VERTICAL SNOW 100 (Weeklys) 29 MAY 26 260/262.5 CALL @.05 LMT GTC"
#   "(Replacing #1006409450039) BUY +1 VERTICAL SNOW 100 (Weeklys) 22 MAY 26 175/180 CALL @2.08 LMT"
#   "BUY +1 CRM 100 17 JUL 26 150 PUT @1.29 LMT GTC"
#   "BUY +1 BUTTERFLY SMH 100 (Weeklys) 29 MAY 26 550/530/510 PUT @.32 LMT"
#   "BUY +1 1/2 BACKRATIO NFLX 100 (Weeklys) 24 APR 26 89/86 PUT @.23 LMT GTC"
#   "SELL -1 DIAGONAL NKE 100 21 JAN 28/24 APR 26 45/52 PUT @.85 LMT"

_ORDER_RE = re.compile(
    r"(?:\(Replacing[^)]+\)\s*)?"  # Optional replacing prefix
    r"(?P<dir>BUY|SELL)\s+"
    r"(?P<signed_qty>[+-]\d+)\s+"
    r"(?:(?P<ratio>\d+/\d+)\s+)?"  # Optional ratio like "1/2"
    r"(?:(?P<strat>VERTICAL|BUTTERFLY|IRON\s+CONDOR|IRON\s+BUTTERFLY|"
    r"CALENDAR|DIAGONAL|STRANGLE|STRADDLE|BACKRATIO)\s+)?"
    r"(?P<sym>[A-Z]+)\s+"
    r"100\s+"
    r"(?:\(Weeklys\)\s+)?"
    r"(?P<exp>[\d]{1,2}\s+[A-Z]{3}\s+\d{2}(?:/[\d]{1,2}\s+[A-Z]{3}\s+\d{2})?)\s+"  # Single or dual exp
    r"(?P<strikes>[\d./]+)\s+"
    r"(?P<otype>CALL|PUT)\s+"
    r"@(?P<price>-?[\d.]+)",
    re.IGNORECASE,
)


def parse_order_confirmation(text: str) -> Optional[dict]:
    """
    Parse an order confirmation line into trade details.

    Returns dict with:
        direction, qty, strategy_label, underlying, expiration,
        strikes, option_type, net_price
    Or None if parsing fails.
    """
    text = text.strip()
    m = _ORDER_RE.match(text)
    if not m:
        return None

    # Parse expiration (may be single or dual for DIAGONAL/CALENDAR)
    exp_str = m.group("exp")
    if "/" in exp_str and m.group("strat") and m.group("strat").upper() in ("DIAGONAL", "CALENDAR"):
        # Dual expiration - use the far (first) one as the trade expiration
        exp_parts = exp_str.split("/")
        expiration = _parse_exp_words(exp_parts[0].strip())
    else:
        expiration = _parse_exp_words(exp_str)

    # Parse strikes
    strikes_str = m.group("strikes")
    strikes = [float(s) for s in strikes_str.split("/") if s]

    # Strategy label
    strat = m.group("strat")
    if strat:
        strat = strat.strip().upper().replace(" ", "_")
    else:
        strat = "SINGLE"

    # Handle BACKRATIO - treat as the base strategy type
    if strat == "BACKRATIO":
        strat = "BACKRATIO"

    return {
        "direction": Side.SELL if m.group("dir").upper() == "SELL" else Side.BUY,
        "qty": abs(int(m.group("signed_qty"))),
        "strategy_label": strat,
        "underlying": m.group("sym").upper(),
        "expiration": expiration,
        "strikes": strikes,
        "option_type": OptionType.CALL if m.group("otype").upper() == "CALL" else OptionType.PUT,
        "net_price": float(m.group("price")),
        "ratio": m.group("ratio"),  # For back ratios like "1/2"
    }

_RAD_RE = re.compile(
    r"Removed due to (?P<reason>Expiration|Assignment)\s+"
    r"(?P<otype>CALL|PUT)\s+"
    r"(?P<name>.+?)\s+\$(?P<strike>[\d.]+)\s+"
    r"EXP\s+(?P<exp>[\d/]+):\s+EXP:\s+(?P<qty>-?[\d.]+)",
    re.IGNORECASE,
)

_RAD_SYM_RE = re.compile(r"\.?([A-Z]+)\d{6}[CP][\d.]+$")

# EXP: Stock delivery from assignment/exercise
# "BOT 200.0 SNOW UPON SNOWFLAKE INC CLASS CLASS A"
# "SOLD -100.0 AAPL UPON APPLE INC"
_EXP_RE = re.compile(
    r"^(?P<dir>SOLD|BOT)\s+"
    r"(?P<qty>-?[\d.]+)\s+"
    r"(?P<sym>[A-Z]+)\s+"
    r"UPON\s+",
    re.IGNORECASE,
)


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


def _parse_roll(desc: str) -> Optional[dict]:
    """
    Parse a DIAGONAL/CALENDAR roll with two expirations.

    Example: "SOLD -1 DIAGONAL NKE 100 21 JAN 28/24 APR 26 45/52 PUT @.85"
    - exp_far = 21 JAN 28 (the new/far leg being opened)
    - exp_near = 24 APR 26 (the old/near leg being closed)
    - strikes = 45/52 (far strike / near strike)

    SOLD DIAGONAL = close near leg (buy back), open far leg (sell)
    BOT DIAGONAL = close near leg (sell), open far leg (buy)

    Returns dict with 'close_leg' and 'open_leg' sub-dicts.
    """
    m = _TRD_ROLL_RE.match(desc.strip())
    if not m:
        return None

    strikes = [float(s) for s in m.group("strikes").split("/") if s]
    strike_far = strikes[0] if len(strikes) >= 1 else None
    strike_near = strikes[1] if len(strikes) >= 2 else strikes[0] if strikes else None

    direction = Side.SELL if m.group("dir").upper() == "SOLD" else Side.BUY
    qty = abs(int(m.group("signed_qty")))
    option_type = OptionType.CALL if m.group("otype").upper() == "CALL" else OptionType.PUT

    # SOLD DIAGONAL: you're selling the spread
    #   - Close near leg by buying it back (BUY)
    #   - Open far leg by selling it (SELL)
    # BOT DIAGONAL: you're buying the spread
    #   - Close near leg by selling it (SELL)
    #   - Open far leg by buying it (BUY)

    if direction == Side.SELL:
        close_dir = Side.BUY
        open_dir = Side.SELL
    else:
        close_dir = Side.SELL
        open_dir = Side.BUY

    return {
        "is_roll": True,
        "underlying": m.group("sym").upper(),
        "qty": qty,
        "option_type": option_type,
        "net_price": float(m.group("price")),
        "close_leg": {
            "direction": close_dir,
            "expiration": _parse_exp_words(m.group("exp_near")),
            "strike": strike_near,
        },
        "open_leg": {
            "direction": open_dir,
            "expiration": _parse_exp_words(m.group("exp_far")),
            "strike": strike_far,
        },
    }


def _parse_exp(desc: str) -> Optional[dict]:
    """
    Parse EXP (stock exercise/assignment delivery) line.

    Example: "BOT 200.0 SNOW UPON SNOWFLAKE INC CLASS CLASS A"
    This means you received 200 shares of SNOW due to put assignment.
    """
    m = _EXP_RE.match(desc.strip())
    if not m:
        return None
    return {
        "direction": Side.SELL if m.group("dir").upper() == "SOLD" else Side.BUY,
        "qty": abs(int(float(m.group("qty")))),
        "underlying": m.group("sym").upper(),
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
    Tracks open positions per underlying with quantity tracking.

    Key behaviors:
    - Tracks open_qty for each position
    - Same-direction events ADD to existing position (scale-in)
    - Opposite-direction events CLOSE position (full or partial)
    - Position removed when open_qty reaches 0

    direction = SELL means net short (credit spread opened with SOLD)
                BUY  means net long (debit spread opened with BOT)
    """

    def __init__(self):
        # underlying -> list of open position dicts
        self._positions: dict[str, list[dict]] = {}

    def find_matching_position(self, event: CashEvent) -> Optional[dict]:
        """Find a position matching this event's contract specs."""
        for pos in self._positions.get(event.underlying, []):
            if self._contracts_match(pos, event):
                return pos
        return None

    def find_for_close(self, event: CashEvent) -> Optional[dict]:
        """Find an open position that this event would close (opposite direction)."""
        for pos in self._positions.get(event.underlying, []):
            if not self._contracts_match(pos, event):
                continue
            # A close reverses the direction
            open_dir = pos["direction"]
            if open_dir == Side.SELL and event.direction == Side.BUY:
                return pos
            if open_dir == Side.BUY and event.direction == Side.SELL:
                return pos
        return None

    def find_for_add(self, event: CashEvent) -> Optional[dict]:
        """Find an open position to add to (same direction = scale-in)."""
        for pos in self._positions.get(event.underlying, []):
            if not self._contracts_match(pos, event):
                continue
            # Same direction = adding to position
            if pos["direction"] == event.direction:
                return pos
        return None

    def add_position(self, event: CashEvent, trade: Trade) -> None:
        """Create a new open position."""
        if event.underlying not in self._positions:
            self._positions[event.underlying] = []
        self._positions[event.underlying].append({
            "direction": event.direction,
            "strikes": set(event.strikes),
            "expiration": event.expiration,
            "option_type": event.option_type,
            "open_qty": event.qty,
            "trade": trade,
        })

    def add_to_position(self, pos: dict, event: CashEvent) -> None:
        """Add quantity to existing position (scale-in)."""
        pos["open_qty"] += event.qty

    def reduce_position(self, pos: dict, qty: int) -> bool:
        """Reduce position quantity. Returns True if fully closed."""
        pos["open_qty"] -= qty
        if pos["open_qty"] <= 0:
            self._remove_position(pos)
            return True
        return False

    def _remove_position(self, pos: dict) -> None:
        """Remove a position from tracking."""
        for sym, positions in self._positions.items():
            self._positions[sym] = [p for p in positions if p is not pos]

    def remove_trade(self, trade: Trade) -> None:
        """Remove all positions for a trade."""
        for sym, positions in self._positions.items():
            self._positions[sym] = [p for p in positions if p["trade"] is not trade]

    def find_for_expiration(self, event: CashEvent) -> Optional[dict]:
        """Match RAD event to open position. Strike nearest match within open strikes."""
        for pos in self._positions.get(event.underlying, []):
            if pos["expiration"] != event.expiration:
                continue
            if pos["option_type"] != event.option_type:
                continue
            # Any of the event's strikes overlap with open strikes
            if event.strikes and pos["strikes"] & set(event.strikes):
                return pos
            # Fallback: strike within $0.01
            if event.strikes:
                for open_strike in pos["strikes"]:
                    if abs(open_strike - event.strikes[0]) < 0.01:
                        return pos
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

    def get_open_qty(self, trade: Trade) -> int:
        """Get total open quantity for a trade."""
        total = 0
        for positions in self._positions.values():
            for p in positions:
                if p["trade"] is trade:
                    total += p["open_qty"]
        return total


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
            if type_ not in ("TRD", "RAD", "EXP"):
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
                # Try to parse as a DIAGONAL/CALENDAR roll first
                roll = _parse_roll(desc)
                if roll:
                    # Roll = two events: close near leg + open far leg
                    # For P&L: attribute all amount/fees to the close leg
                    close_event = CashEvent(
                        ref=f"{ref}_CLOSE", date=parsed_date, time_str=time_str,
                        event_type=EventType.CLOSE,
                        description=f"[ROLL CLOSE] {desc}",
                        direction=roll["close_leg"]["direction"],
                        qty=roll["qty"],
                        strategy_label="SINGLE",
                        underlying=roll["underlying"],
                        expiration=roll["close_leg"]["expiration"],
                        strikes=[roll["close_leg"]["strike"]] if roll["close_leg"]["strike"] else [],
                        option_type=roll["option_type"],
                        net_price=roll["net_price"],
                        amount=amt, misc_fees=misc, commissions=comm,
                    )
                    open_event = CashEvent(
                        ref=f"{ref}_OPEN", date=parsed_date, time_str=time_str,
                        event_type=EventType.OPEN,
                        description=f"[ROLL OPEN] {desc}",
                        direction=roll["open_leg"]["direction"],
                        qty=roll["qty"],
                        strategy_label="SINGLE",
                        underlying=roll["underlying"],
                        expiration=roll["open_leg"]["expiration"],
                        strikes=[roll["open_leg"]["strike"]] if roll["open_leg"]["strike"] else [],
                        option_type=roll["option_type"],
                        net_price=0.0,  # Price already in close leg
                        amount=0.0, misc_fees=0.0, commissions=0.0,
                    )
                    events.append(close_event)
                    events.append(open_event)
                    logger.info("Parsed roll: %s -> close %s, open %s",
                                roll["underlying"],
                                roll["close_leg"]["expiration"],
                                roll["open_leg"]["expiration"])
                    continue

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

            elif type_ == "RAD":
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

            elif type_ == "EXP":
                # Stock delivery from assignment/exercise
                parsed = _parse_exp(desc)
                if not parsed:
                    logger.warning("Could not parse EXP description: %s", desc)
                    continue
                event = CashEvent(
                    ref=ref, date=parsed_date, time_str=time_str,
                    event_type=EventType.STOCK_DELIVERY,
                    description=desc,
                    direction=parsed["direction"],
                    underlying=parsed["underlying"],
                    qty=parsed["qty"],
                    amount=amt, misc_fees=misc, commissions=comm,
                )
                events.append(event)
                logger.info("Parsed stock delivery: %s %s %d shares",
                            parsed["direction"], parsed["underlying"], parsed["qty"])

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
        """
        Build trades from cash events with proper quantity tracking.

        Logic:
        - Same direction as existing position = scale-in (add to position)
        - Opposite direction = close (full or partial based on qty)
        - RAD events close positions on expiration/assignment
        """
        tracker = PositionTracker()
        all_trades: list[Trade] = []

        for event in events:
            if not event.underlying:
                continue

            # ── STOCK_DELIVERY: from assignment/exercise ────────────────
            if event.event_type == EventType.STOCK_DELIVERY:
                # Find the most recent trade for this underlying that was assigned
                # and attach the stock delivery event to it
                for trade in reversed(all_trades):
                    if trade.underlying == event.underlying:
                        # Check if this trade has an assignment event
                        has_assignment = any(
                            e.event_type == EventType.ASSIGNMENT
                            for e in trade.close_events
                        )
                        if has_assignment:
                            trade.close_events.append(event)
                            trade.recalculate()
                            logger.info("Attached stock delivery to %s trade", event.underlying)
                            break
                else:
                    logger.warning(
                        "STOCK_DELIVERY %s — no assigned trade found",
                        event.underlying
                    )
                continue

            # ── RAD: expiration or assignment ──────────────────────────
            if event.event_type in (EventType.EXPIRATION, EventType.ASSIGNMENT):
                pos = tracker.find_for_expiration(event)
                if pos:
                    trade = pos["trade"]
                    trade.close_events.append(event)
                    # RAD typically closes entire position
                    trade.is_expired = (event.event_type == EventType.EXPIRATION)
                    trade.is_closed = True
                    trade.close_time = event.exec_datetime
                    tracker.remove_trade(trade)
                    trade.recalculate()
                else:
                    logger.warning(
                        "RAD %s %s %s — no open trade found (opened before export window)",
                        event.underlying, event.option_type, event.strikes
                    )
                continue

            # ── TRD: check if this closes or adds to existing position ──
            close_pos = tracker.find_for_close(event)

            if close_pos:
                # Opposite direction = closing (full or partial)
                event.event_type = EventType.CLOSE
                trade = close_pos["trade"]
                trade.close_events.append(event)
                trade.close_time = event.exec_datetime

                # Reduce position quantity
                fully_closed = tracker.reduce_position(close_pos, event.qty)
                if fully_closed:
                    trade.is_closed = True
                trade.recalculate()
                continue

            # Check if this adds to existing position (same direction = scale-in)
            add_pos = tracker.find_for_add(event)

            if add_pos:
                # Same direction = adding to position (scale-in)
                event.event_type = EventType.OPEN
                trade = add_pos["trade"]
                trade.open_events.append(event)
                tracker.add_to_position(add_pos, event)
                trade.recalculate()
                continue

            # No existing position - create new trade
            event.event_type = EventType.OPEN
            trade = Trade(
                underlying=event.underlying,
                spread_label=event.strategy_label,
                expiration=event.expiration,
                open_time=event.exec_datetime,
            )
            trade.open_events.append(event)
            trade.recalculate()
            tracker.add_position(event, trade)
            all_trades.append(trade)

        # Auto-close trades that have expired (no RAD event but past expiration)
        today = date.today()
        for trade in all_trades:
            if not trade.is_closed and trade.expiration and trade.expiration < today:
                trade.is_closed = True
                trade.is_expired = True
                # Set close_time to expiration date at market close
                trade.close_time = datetime.combine(trade.expiration, datetime.strptime("16:00:00", "%H:%M:%S").time())
                trade.recalculate()
                logger.info(
                    "Auto-closed expired trade: %s %s exp %s (no RAD event)",
                    trade.underlying, trade.strategy, trade.expiration
                )

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
