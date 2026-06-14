"""Trade endpoints."""

from datetime import date
from fastapi import APIRouter, Query, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from database import get_db
from services.trade_service import TradeService
from models.schemas import TradeListItem, TradeListResponse, TradeDetail
from auth import get_current_user_id

router = APIRouter()


@router.get("", response_model=TradeListResponse)
async def list_trades(
    underlying: Optional[str] = Query(None),
    strategy: Optional[str] = Query(None),
    status: Optional[str] = Query(None, pattern="^(open|closed)$"),
    date_from: Optional[date] = Query(None, description="Filter by open date (from)"),
    date_to: Optional[date] = Query(None, description="Filter by open date (to)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    List trades with optional filters.

    Filters:
    - underlying: Filter by ticker symbol
    - strategy: Filter by strategy type
    - status: "open" or "closed"
    - date_from: Filter by open date (from)
    - date_to: Filter by open date (to)
    """
    service = TradeService(db)

    try:
        data_key = service.get_user_data_key(user_id)
    except ValueError:
        # No profile yet - return empty
        return TradeListResponse(trades=[], total=0, page=page, page_size=page_size)

    is_closed = None
    if status == "open":
        is_closed = False
    elif status == "closed":
        is_closed = True

    result = service.list_trades(
        owner_key=data_key,
        underlying=underlying,
        strategy=strategy,
        is_closed=is_closed,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )

    # Convert ORM objects to Pydantic
    trades = [
        TradeListItem.model_validate(t)
        for t in result["trades"]
    ]

    return TradeListResponse(
        trades=trades,
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.get("/strategies")
async def list_strategies(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Get list of unique strategies used in trades."""
    service = TradeService(db)

    try:
        data_key = service.get_user_data_key(user_id)
    except ValueError:
        return []

    strategies = service.get_unique_strategies(data_key)
    return strategies


@router.get("/{trade_id}")
async def get_trade(
    trade_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Get full trade detail including legs and cash events."""
    service = TradeService(db)

    try:
        data_key = service.get_user_data_key(user_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Trade not found")

    trade = service.get_trade_detail(data_key, trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    return trade


class NotesUpdate(BaseModel):
    notes: str


class QuickAddRequest(BaseModel):
    text: str


class QuickAddResponse(BaseModel):
    success: bool
    trade_id: Optional[str] = None
    message: str
    parsed: Optional[dict] = None


@router.post("/quick-add", response_model=QuickAddResponse)
async def quick_add_trade(
    request: QuickAddRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    Quick-add a trade from order confirmation text.

    Parses text like:
    - "BUY +2 VERTICAL SNOW 100 (Weeklys) 29 MAY 26 260/262.5 CALL @.05 LMT GTC"
    - "SELL -1 DIAGONAL NKE 100 21 JAN 28/24 APR 26 45/52 PUT @.85 LMT"

    Returns parsed details for preview, or creates trade if confirmed.
    """
    from parser.tos_parser import parse_order_confirmation

    service = TradeService(db)

    try:
        data_key = service.get_user_data_key(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="User profile not found")

    # Parse the order text
    parsed = parse_order_confirmation(request.text)
    if not parsed:
        return QuickAddResponse(
            success=False,
            message="Could not parse order text. Expected format like: BUY +1 VERTICAL SNOW 100 29 MAY 26 260/262.5 CALL @.05 LMT",
            parsed=None,
        )

    # Create or update the trade
    result = service.create_trade_from_order(data_key, parsed)

    return QuickAddResponse(
        success=True,
        trade_id=result["trade_id"],
        message=result["message"],
        parsed={
            "direction": parsed["direction"].value,
            "qty": parsed["qty"],
            "underlying": parsed["underlying"],
            "strategy_label": parsed["strategy_label"],
            "strikes": parsed["strikes"],
            "option_type": parsed["option_type"].value,
            "expiration": parsed["expiration"].isoformat() if parsed["expiration"] else None,
            "net_price": parsed["net_price"],
            "action": result["action"],
        },
    )


@router.put("/{trade_id}/notes")
async def update_trade_notes(
    trade_id: str,
    notes: str = Query(...),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Update notes for a trade."""
    service = TradeService(db)

    try:
        data_key = service.get_user_data_key(user_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Trade not found")

    success = service.update_trade_notes(data_key, trade_id, notes)
    if not success:
        raise HTTPException(status_code=404, detail="Trade not found")

    return {"id": trade_id, "notes": notes}


@router.delete("/{trade_id}")
async def delete_trade(
    trade_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Delete a trade and its associated cash events."""
    service = TradeService(db)

    try:
        data_key = service.get_user_data_key(user_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Trade not found")

    success = service.delete_trade(data_key, trade_id)
    if not success:
        raise HTTPException(status_code=404, detail="Trade not found")

    return {"id": trade_id, "deleted": True}
