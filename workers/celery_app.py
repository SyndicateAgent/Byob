from celery import Celery  # type: ignore[import-untyped]

from api.app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "kb_platform_workers",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.update(
    task_acks_late=True,
    task_default_queue="ingestion",
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)
