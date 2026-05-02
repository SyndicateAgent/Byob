from sys import platform

from celery import Celery  # type: ignore[import-untyped]
from celery.signals import worker_init  # type: ignore[import-untyped]

from api.app.config import get_settings
from api.app.core.clip_embedding import ClipEmbeddingClient

settings = get_settings()

celery_app = Celery(
    "byob_workers",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["workers.tasks.document_tasks"],
)
celery_app.conf.update(
    task_acks_late=True,
    task_default_queue="ingestion",
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)

if platform == "win32":
    celery_app.conf.update(
        worker_pool="solo",
        worker_concurrency=1,
    )


@worker_init.connect  # type: ignore[misc]
def preload_clip_model_on_worker_startup(**_: object) -> None:
    """Download and load CLIP before the worker starts processing ingestion tasks."""

    if not settings.clip_preload_on_startup:
        return
    ClipEmbeddingClient(settings).warmup_sync()
