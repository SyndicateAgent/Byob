from workers.celery_app import celery_app


def test_document_ingestion_task_is_registered() -> None:
    """The ingestion worker must know the task name emitted by the API."""

    celery_app.loader.import_default_modules()

    assert "workers.tasks.document_tasks.process_document" in celery_app.tasks
