"""Authentication module - Supabase JWT verification."""

from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt

from config import get_settings

# Dev user ID for testing
DEV_USER_ID = "00000000-0000-0000-0000-000000000001"

security = HTTPBearer(auto_error=False)


def verify_supabase_token(token: str) -> dict:
    """Verify a Supabase JWT token and return the payload."""
    settings = get_settings()
    try:
        # Supabase uses HS256 with the JWT secret
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
        )


async def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """Get the current user ID from the JWT token.

    In dev mode, returns the dev user ID.
    In production, verifies the Supabase JWT and returns the user ID.
    """
    settings = get_settings()
    if settings.dev_mode:
        return DEV_USER_ID

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    payload = verify_supabase_token(credentials.credentials)
    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: no user ID",
        )

    return user_id


async def get_optional_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[str]:
    """Get the current user ID if authenticated, None otherwise."""
    settings = get_settings()
    if settings.dev_mode:
        return DEV_USER_ID

    if credentials is None:
        return None

    try:
        payload = verify_supabase_token(credentials.credentials)
        return payload.get("sub")
    except HTTPException:
        return None
