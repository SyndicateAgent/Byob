from workers.celery_app import celery_app, worker_runtime_options


def test_document_ingestion_task_is_registered() -> None:
    """The ingestion worker must know the task name emitted by the API."""

    celery_app.loader.import_default_modules()

    assert "workers.tasks.document_tasks.process_document" in celery_app.tasks


def test_document_ingestion_task_does_not_retry_value_errors() -> None:
    """Permanent parser errors should fail once instead of looping retries."""

    celery_app.loader.import_default_modules()
    task = celery_app.tasks["workers.tasks.document_tasks.process_document"]

    assert task.dont_autoretry_for == (ValueError,)


def test_windows_worker_uses_solo_pool() -> None:
    """Windows workers should avoid Celery's process pool."""

    assert worker_runtime_options("win32", 4) == {
        "worker_pool": "solo",
        "worker_concurrency": 1,
    }


def test_linux_worker_uses_configured_prefork_concurrency() -> None:
    """Linux and container workers should process multiple ingestion jobs concurrently."""

    assert worker_runtime_options("linux", 4) == {
        "worker_pool": "prefork",
        "worker_concurrency": 4,
    }
