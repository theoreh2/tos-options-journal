"""Analytics endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from services.trade_service import TradeService
from models.schemas import AnalyticsSummary, StrategyBreakdown, UnderlyingBreakdown
from auth import get_current_user_id

router = APIRouter()


@router.get("/summary", response_model=AnalyticsSummary)
async def get_summary(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Get overall P&L summary."""
    service = TradeService(db)

    try:
        data_key = service.get_user_data_key(user_id)
    except ValueError:
        # No profile yet - return zeros
        return AnalyticsSummary(
            total_trades=0,
            closed_trades=0,
            open_trades=0,
            total_pnl_gross=0,
            total_pnl_net=0,
            total_fees=0,
            win_count=0,
            loss_count=0,
            win_rate=0,
            avg_winner=0,
            avg_loser=0,
        )

    result = service.get_analytics_summary(data_key)
    return AnalyticsSummary(**result)


@router.get("/by-strategy", response_model=list[StrategyBreakdown])
async def get_by_strategy(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Get P&L breakdown by strategy type."""
    service = TradeService(db)

    try:
        data_key = service.get_user_data_key(user_id)
    except ValueError:
        return []

    return service.get_analytics_by_strategy(data_key)


@router.get("/by-underlying", response_model=list[UnderlyingBreakdown])
async def get_by_underlying(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Get P&L breakdown by underlying symbol."""
    service = TradeService(db)

    try:
        data_key = service.get_user_data_key(user_id)
    except ValueError:
        return []

    return service.get_analytics_by_underlying(data_key)


@router.get("/over-time")
async def get_pnl_over_time(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Get cumulative P&L over time."""
    service = TradeService(db)

    try:
        data_key = service.get_user_data_key(user_id)
    except ValueError:
        return []

    return service.get_pnl_over_time(data_key)
