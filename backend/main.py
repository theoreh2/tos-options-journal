"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from routers import imports, trades, analytics

settings = get_settings()

app = FastAPI(
    title="Options Trade Journal API",
    description="API for tracking options trades, P&L, and strategy performance",
    version="0.1.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(imports.router, prefix="/api/import", tags=["Import"])
app.include_router(trades.router, prefix="/api/trades", tags=["Trades"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "app": "Options Trade Journal",
        "docs": "/docs",
        "health": "/health",
    }
