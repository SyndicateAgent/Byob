from fastapi import APIRouter

from api.app.api.v1.auth import router as auth_router
from api.app.api.v1.usage import router as usage_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(usage_router)

__all__ = ["router"]
"""Versioned API namespace for future /api/v1 routes."""
