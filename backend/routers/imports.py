"""Import endpoints for CSV uploads."""

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from services.trade_service import TradeService
from models.schemas import ImportResult
from auth import get_current_user_id

router = APIRouter()


@router.post("/tos", response_model=ImportResult)
async def import_tos_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    Import a thinkorswim Account Statement CSV export.

    Parses the CSV, extracts trades, and upserts to database.
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    # Read file content
    content = await file.read()
    try:
        content_str = content.decode("utf-8")
    except UnicodeDecodeError:
        # Try latin-1 as fallback
        content_str = content.decode("latin-1")

    # Import using trade service
    service = TradeService(db)
    try:
        result = service.import_tos_csv(
            user_id=user_id,
            content=content_str,
            filename=file.filename,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ImportResult(**result)
