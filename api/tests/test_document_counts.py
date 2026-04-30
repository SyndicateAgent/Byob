from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.models.knowledge_base import KnowledgeBase
from api.app.services.document_service import refresh_knowledge_base_counts


class FakeSession:
    def __init__(self, knowledge_base: KnowledgeBase) -> None:
        self._values = [knowledge_base, 1, 3]

    async def scalar(self, statement: object) -> object:
        return self._values.pop(0)


@pytest.mark.asyncio
async def test_refresh_knowledge_base_counts_recomputes_from_rows() -> None:
    """KB counters should not drift after repeated reprocessing."""

    knowledge_base = KnowledgeBase(
        id=uuid4(),
        tenant_id=uuid4(),
        name="Test KB",
        qdrant_collection="test_collection",
        document_count=99,
        chunk_count=99,
    )
    session = cast(AsyncSession, FakeSession(knowledge_base))

    await refresh_knowledge_base_counts(session, knowledge_base.id)

    assert knowledge_base.document_count == 1
    assert knowledge_base.chunk_count == 3
