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
