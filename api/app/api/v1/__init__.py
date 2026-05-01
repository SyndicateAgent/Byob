from fastapi import APIRouter

from api.app.api.v1.agent import router as agent_router
from api.app.api.v1.auth import router as auth_router
from api.app.api.v1.documents import router as documents_router
from api.app.api.v1.knowledge_bases import router as knowledge_bases_router
from api.app.api.v1.retrieval import router as retrieval_router
from api.app.api.v1.users import router as users_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(users_router)
router.include_router(knowledge_bases_router)
router.include_router(documents_router)
router.include_router(retrieval_router)
router.include_router(agent_router)

__all__ = ["router"]
