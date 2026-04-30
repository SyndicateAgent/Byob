from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from api.app.core.minio_client import is_bucket_exists_error


def make_client_error(code: str) -> ClientError:
    return ClientError(
        error_response={"Error": {"Code": code, "Message": "test error"}},
        operation_name="CreateBucket",
    )


def test_bucket_exists_errors_are_idempotent_successes() -> None:
    """MinIO/S3 bucket creation should be idempotent for existing owned buckets."""

    assert is_bucket_exists_error(make_client_error("BucketAlreadyOwnedByYou"))
    assert is_bucket_exists_error(make_client_error("BucketAlreadyExists"))
    assert not is_bucket_exists_error(make_client_error("AccessDenied"))
