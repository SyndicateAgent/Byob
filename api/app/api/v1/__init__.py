from fastapi import APIRouter

from api.app.api.v1.auth import router as auth_router
from api.app.api.v1.documents import router as documents_router
from api.app.api.v1.knowledge_bases import router as knowledge_bases_router
from api.app.api.v1.usage import router as usage_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(knowledge_bases_router)
router.include_router(documents_router)
router.include_router(usage_router)

__all__ = ["router"]
