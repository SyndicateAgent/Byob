from asyncio import run
from uuid import UUID

from api.app.config import get_settings
from api.app.services.ingestion_service import process_document_by_id
from workers.celery_app import celery_app


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def process_document(self: object, document_id: str) -> None:
    """Run the document ingestion pipeline for one document."""

    run(process_document_by_id(get_settings(), UUID(document_id)))
