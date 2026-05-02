from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.core.qdrant_client import visual_collection_name
from api.app.deps import get_current_user, get_current_user_or_query_token, get_db_session
from api.app.models.document import Document
from api.app.schemas.auth import CurrentUser
from api.app.schemas.document import (
    ChunkListResponse,
    ChunkResponse,
    DocumentAssetListResponse,
    DocumentAssetResponse,
    DocumentAuditLogListResponse,
    DocumentBatchUploadItem,
    DocumentBatchUploadResponse,
    DocumentContentResponse,
    DocumentContentUpdateRequest,
    DocumentGovernanceInput,
    DocumentGovernanceUpdateRequest,
    DocumentListResponse,
    DocumentResponse,
    DocumentTextCreateRequest,
    DocumentUrlCreateRequest,
    DocumentVersionListResponse,
    ReviewStatus,
)
from api.app.services.document_service import (
    AuditActor,
    create_file_document,
    create_text_document,
    create_url_document,
    delete_document,
    document_generated_object_prefix,
    document_governance_payload,
    document_source_object_key,
    find_duplicate_document,
    get_document,
    get_document_asset,
    hash_content,
    list_chunks,
    list_document_assets,
    list_document_audit_logs,
    list_document_qdrant_point_ids,
    list_document_versions,
    list_document_visual_point_ids,
    list_documents,
    parsed_content_metadata,
    reset_document_for_reprocess,
    update_document_content_source,
    update_document_governance,
)
from api.app.services.knowledge_base_service import get_knowledge_base
from workers.tasks.document_tasks import process_document

router = APIRouter(tags=["documents"])
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
AssetUserDep = Annotated[CurrentUser, Depends(get_current_user_or_query_token)]
UploadFileField = Annotated[UploadFile, File()]
BatchUploadFilesField = Annotated[list[UploadFile], File()]
GovernanceSourceTypeField = Annotated[str, Form(min_length=1, max_length=100)]
AuthorityLevelField = Annotated[int, Form(ge=1)]
ReviewStatusField = Annotated[ReviewStatus, Form()]
BatchSkipReason = Literal["duplicate_name", "duplicate_file_hash", "empty_file"]


def enqueue_document(document_id: UUID) -> None:
    """Queue asynchronous document processing."""

    process_document.delay(str(document_id))


def current_actor(current_user: CurrentUser) -> AuditActor:
    """Return the current user identity for version and audit records."""

    return AuditActor(user_id=current_user.id, email=current_user.email)


def governance_input(
    governance_source_type: str,
    authority_level: int,
    review_status: ReviewStatus,
) -> DocumentGovernanceInput:
    """Build the required governance labels for multipart imports."""

    return DocumentGovernanceInput(
        governance_source_type=governance_source_type,
        authority_level=authority_level,
        review_status=review_status,
    )


async def clear_retrieval_cache(request: Request) -> None:
    """Invalidate retrieval cache after document content or governance changes."""

    redis_client = getattr(request.app.state, "redis_client", None)
    if redis_client is None or not hasattr(redis_client, "delete_prefix"):
        return
    await redis_client.delete_prefix("retrieval:")


async def delete_generated_document_objects(request: Request, document: Document) -> None:
    """Delete parsed content snapshots and extracted assets for one document."""

    await request.app.state.minio_client.delete_prefix(document_generated_object_prefix(document))


async def delete_all_document_objects(request: Request, document: Document) -> None:
    """Delete original and generated MinIO objects for one document."""

    await delete_generated_document_objects(request, document)
    await request.app.state.minio_client.delete_object(document_source_object_key(document))


def skipped_upload_item(
    *,
    filename: str,
    reason: BatchSkipReason,
    document: object | None = None,
) -> DocumentBatchUploadItem:
    """Build a skipped batch upload item with a human-readable reason."""

    detail_by_reason = {
        "duplicate_name": "Skipped because a document with the same name already exists.",
        "duplicate_file_hash": "Skipped because a document with the same file hash already exists.",
        "empty_file": "Skipped because the uploaded file is empty.",
    }
    return DocumentBatchUploadItem(
        filename=filename,
        status="skipped",
        reason=reason,
        detail=detail_by_reason[reason],
        document=DocumentResponse.model_validate(document) if document is not None else None,
    )


@router.post(
    "/knowledge-bases/{kb_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document_endpoint(
    kb_id: UUID,
    request: Request,
    response: Response,
    current_user: CurrentUserDep,
    session: DbSession,
    file: UploadFileField,
    governance_source_type: GovernanceSourceTypeField,
    authority_level: AuthorityLevelField,
    review_status: ReviewStatusField,
) -> DocumentResponse:
    """Upload a file document and enqueue ingestion."""

    knowledge_base = await get_knowledge_base(session, kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    file_type = (file.filename or "document").rsplit(".", maxsplit=1)[-1].lower()
    file_hash = hash_content(content)
    duplicate = await find_duplicate_document(
        session,
        knowledge_base,
        name=file.filename or "document",
        file_hash=file_hash,
    )
    if duplicate is not None:
        response.status_code = status.HTTP_200_OK
        return DocumentResponse.model_validate(duplicate.document)

    object_key = f"knowledge_bases/{kb_id}/{file_hash}"
    await request.app.state.minio_client.put_object(
        object_key,
        content,
        file.content_type or "application/octet-stream",
    )
    document = await create_file_document(
        session,
        knowledge_base,
        name=file.filename or "document",
        file_type=file_type,
        file_size=len(content),
        minio_path=object_key,
        file_hash=file_hash,
        governance=governance_input(governance_source_type, authority_level, review_status),
        actor=current_actor(current_user),
    )
    enqueue_document(document.id)
    await clear_retrieval_cache(request)
    return DocumentResponse.model_validate(document)


@router.post(
    "/knowledge-bases/{kb_id}/documents/batch",
    response_model=DocumentBatchUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_documents_batch_endpoint(
    kb_id: UUID,
    request: Request,
    response: Response,
    current_user: CurrentUserDep,
    session: DbSession,
    files: BatchUploadFilesField,
    governance_source_type: GovernanceSourceTypeField,
    authority_level: AuthorityLevelField,
    review_status: ReviewStatusField,
) -> DocumentBatchUploadResponse:
    """Upload multiple file documents and skip duplicates by name or content hash."""

    knowledge_base = await get_knowledge_base(session, kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one file is required",
        )

    items: list[DocumentBatchUploadItem] = []
    for file in files:
        filename = file.filename or "document"
        content = await file.read()
        if not content:
            items.append(skipped_upload_item(filename=filename, reason="empty_file"))
            continue

        file_hash = hash_content(content)
        duplicate = await find_duplicate_document(
            session,
            knowledge_base,
            name=filename,
            file_hash=file_hash,
        )
        if duplicate is not None:
            items.append(
                skipped_upload_item(
                    filename=filename,
                    reason=duplicate.reason,
                    document=duplicate.document,
                )
            )
            continue

        file_type = filename.rsplit(".", maxsplit=1)[-1].lower()
        object_key = f"knowledge_bases/{kb_id}/{file_hash}"
        await request.app.state.minio_client.put_object(
            object_key,
            content,
            file.content_type or "application/octet-stream",
        )
        document = await create_file_document(
            session,
            knowledge_base,
            name=filename,
            file_type=file_type,
            file_size=len(content),
            minio_path=object_key,
            file_hash=file_hash,
            governance=governance_input(governance_source_type, authority_level, review_status),
            actor=current_actor(current_user),
        )
        enqueue_document(document.id)
        items.append(
            DocumentBatchUploadItem(
                filename=filename,
                status="created",
                document=DocumentResponse.model_validate(document),
            )
        )

    created_count = sum(1 for item in items if item.status == "created")
    skipped_count = len(items) - created_count
    if created_count == 0:
        response.status_code = status.HTTP_200_OK
    else:
        await clear_retrieval_cache(request)
    return DocumentBatchUploadResponse(
        request_id=request.state.request_id,
        created_count=created_count,
        skipped_count=skipped_count,
        items=items,
    )


@router.post(
    "/knowledge-bases/{kb_id}/documents/text",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_text_document_endpoint(
    kb_id: UUID,
    payload: DocumentTextCreateRequest,
    request: Request,
    response: Response,
    current_user: CurrentUserDep,
    session: DbSession,
) -> DocumentResponse:
    """Create a document from direct text input and enqueue ingestion."""

    knowledge_base = await get_knowledge_base(session, kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    duplicate = await find_duplicate_document(
        session,
        knowledge_base,
        name=payload.name,
        file_hash=hash_content(payload.content.encode("utf-8")),
    )
    if duplicate is not None:
        response.status_code = status.HTTP_200_OK
        return DocumentResponse.model_validate(duplicate.document)

    document = await create_text_document(
        session,
        knowledge_base,
        payload,
        actor=current_actor(current_user),
    )
    enqueue_document(document.id)
    await clear_retrieval_cache(request)
    return DocumentResponse.model_validate(document)


@router.post(
    "/knowledge-bases/{kb_id}/documents/url",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_url_document_endpoint(
    kb_id: UUID,
    payload: DocumentUrlCreateRequest,
    request: Request,
    response: Response,
    current_user: CurrentUserDep,
    session: DbSession,
) -> DocumentResponse:
    """Create a document from a URL and enqueue ingestion."""

    knowledge_base = await get_knowledge_base(session, kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    source_url = str(payload.url)
    duplicate = await find_duplicate_document(
        session,
        knowledge_base,
        name=payload.name or source_url,
        file_hash=None,
    )
    if duplicate is not None:
        response.status_code = status.HTTP_200_OK
        return DocumentResponse.model_validate(duplicate.document)

    document = await create_url_document(
        session,
        knowledge_base,
        payload,
        actor=current_actor(current_user),
    )
    enqueue_document(document.id)
    await clear_retrieval_cache(request)
    return DocumentResponse.model_validate(document)


@router.get("/knowledge-bases/{kb_id}/documents", response_model=DocumentListResponse)
async def list_documents_endpoint(
    kb_id: UUID,
    request: Request,
    current_user: CurrentUserDep,
    session: DbSession,
) -> DocumentListResponse:
    """List documents in a knowledge base."""

    knowledge_base = await get_knowledge_base(session, kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    rows = await list_documents(session, knowledge_base)
    return DocumentListResponse(
        request_id=request.state.request_id,
        data=[DocumentResponse.model_validate(row) for row in rows],
    )


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document_endpoint(
    document_id: UUID,
    current_user: CurrentUserDep,
    session: DbSession,
) -> DocumentResponse:
    """Return document details."""

    document = await get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return DocumentResponse.model_validate(document)


@router.patch("/documents/{document_id}/governance", response_model=DocumentResponse)
async def update_document_governance_endpoint(
    document_id: UUID,
    payload: DocumentGovernanceUpdateRequest,
    request: Request,
    current_user: CurrentUserDep,
    session: DbSession,
) -> DocumentResponse:
    """Update document governance fields and sync filter payloads."""

    document = await get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    knowledge_base = await get_knowledge_base(session, document.kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )

    updated_document = await update_document_governance(
        session,
        document,
        payload,
        actor=current_actor(current_user),
    )
    point_ids = await list_document_qdrant_point_ids(session, updated_document)
    visual_point_ids = await list_document_visual_point_ids(session, updated_document)
    await request.app.state.qdrant_client.set_payload(
        knowledge_base.qdrant_collection,
        point_ids,
        document_governance_payload(updated_document),
    )
    await request.app.state.qdrant_client.set_payload(
        visual_collection_name(knowledge_base.qdrant_collection),
        visual_point_ids,
        document_governance_payload(updated_document),
    )
    await clear_retrieval_cache(request)
    return DocumentResponse.model_validate(updated_document)


@router.get("/documents/{document_id}/versions", response_model=DocumentVersionListResponse)
async def list_document_versions_endpoint(
    document_id: UUID,
    request: Request,
    current_user: CurrentUserDep,
    session: DbSession,
) -> DocumentVersionListResponse:
    """Return document version history."""

    document = await get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    versions = await list_document_versions(session, document)
    return DocumentVersionListResponse(
        request_id=request.state.request_id,
        data=versions,
    )


@router.get("/documents/{document_id}/audit-logs", response_model=DocumentAuditLogListResponse)
async def list_document_audit_logs_endpoint(
    document_id: UUID,
    request: Request,
    current_user: CurrentUserDep,
    session: DbSession,
) -> DocumentAuditLogListResponse:
    """Return document audit log entries."""

    document = await get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    audit_logs = await list_document_audit_logs(session, document)
    return DocumentAuditLogListResponse(
        request_id=request.state.request_id,
        data=audit_logs,
    )


@router.get("/documents/{document_id}/chunks", response_model=ChunkListResponse)
async def list_chunks_endpoint(
    document_id: UUID,
    request: Request,
    current_user: CurrentUserDep,
    session: DbSession,
) -> ChunkListResponse:
    """List persisted chunks for one document."""

    document = await get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    chunks = await list_chunks(session, document)
    return ChunkListResponse(
        request_id=request.state.request_id,
        data=[ChunkResponse.model_validate(chunk) for chunk in chunks],
    )


@router.get("/documents/{document_id}/content", response_model=DocumentContentResponse)
async def get_document_content_endpoint(
    document_id: UUID,
    request: Request,
    current_user: CurrentUserDep,
    session: DbSession,
) -> DocumentContentResponse:
    """Return the parsed full-content snapshot for one document."""

    document = await get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    content_metadata = parsed_content_metadata(document)
    if content_metadata is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parsed document content is not available; reprocess the document first",
        )

    stored_object = await request.app.state.minio_client.get_stored_object(
        str(content_metadata["minio_path"]),
    )
    return DocumentContentResponse(
        request_id=request.state.request_id,
        document_id=document.id,
        content=stored_object.content.decode("utf-8", errors="replace"),
        content_type=str(content_metadata.get("content_type") or stored_object.content_type),
        source="parsed_content",
    )


@router.patch("/documents/{document_id}/content", response_model=DocumentResponse)
async def update_document_content_endpoint(
    document_id: UUID,
    payload: DocumentContentUpdateRequest,
    request: Request,
    current_user: CurrentUserDep,
    session: DbSession,
) -> DocumentResponse:
    """Replace editable source content and enqueue a fresh ingestion run."""

    document = await get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    knowledge_base = await get_knowledge_base(session, document.kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )

    point_ids = await list_document_qdrant_point_ids(session, document)
    visual_point_ids = await list_document_visual_point_ids(session, document)
    await request.app.state.qdrant_client.delete_points(
        knowledge_base.qdrant_collection,
        point_ids,
    )
    await request.app.state.qdrant_client.delete_points(
        visual_collection_name(knowledge_base.qdrant_collection),
        visual_point_ids,
    )
    await delete_all_document_objects(request, document)
    updated_document = await update_document_content_source(
        session,
        document,
        payload,
        actor=current_actor(current_user),
    )
    enqueue_document(updated_document.id)
    await clear_retrieval_cache(request)
    return DocumentResponse.model_validate(updated_document)


@router.get("/documents/{document_id}/assets", response_model=DocumentAssetListResponse)
async def list_document_assets_endpoint(
    document_id: UUID,
    request: Request,
    current_user: CurrentUserDep,
    session: DbSession,
) -> DocumentAssetListResponse:
    """List parsed binary assets for one document."""

    document = await get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    assets = await list_document_assets(session, document)
    return DocumentAssetListResponse(
        request_id=request.state.request_id,
        data=[DocumentAssetResponse.model_validate(asset) for asset in assets],
    )


@router.get("/documents/{document_id}/assets/{asset_id}")
async def get_document_asset_endpoint(
    document_id: UUID,
    asset_id: UUID,
    request: Request,
    current_user: AssetUserDep,
    session: DbSession,
) -> Response:
    """Return one parsed binary asset with backend-controlled access."""

    document = await get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    asset = await get_document_asset(session, document, asset_id)
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document asset not found",
        )

    stored_object = await request.app.state.minio_client.get_stored_object(asset.minio_path)
    return Response(
        content=stored_object.content,
        media_type=asset.content_type or stored_object.content_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document_endpoint(
    document_id: UUID,
    request: Request,
    current_user: CurrentUserDep,
    session: DbSession,
) -> None:
    """Delete a document, its chunks, and corresponding Qdrant points."""

    document = await get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    knowledge_base = await get_knowledge_base(session, document.kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    point_ids = await list_document_qdrant_point_ids(session, document)
    visual_point_ids = await list_document_visual_point_ids(session, document)
    await request.app.state.qdrant_client.delete_points(
        knowledge_base.qdrant_collection,
        point_ids,
    )
    await request.app.state.qdrant_client.delete_points(
        visual_collection_name(knowledge_base.qdrant_collection),
        visual_point_ids,
    )
    await delete_all_document_objects(request, document)
    await delete_document(session, document, actor=current_actor(current_user))
    await clear_retrieval_cache(request)


@router.post("/documents/{document_id}/reprocess", response_model=DocumentResponse)
async def reprocess_document_endpoint(
    document_id: UUID,
    request: Request,
    current_user: CurrentUserDep,
    session: DbSession,
) -> DocumentResponse:
    """Delete old vectors, reset a document, and enqueue ingestion again."""

    document = await get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    knowledge_base = await get_knowledge_base(session, document.kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    point_ids = await list_document_qdrant_point_ids(session, document)
    visual_point_ids = await list_document_visual_point_ids(session, document)
    await request.app.state.qdrant_client.delete_points(
        knowledge_base.qdrant_collection,
        point_ids,
    )
    await request.app.state.qdrant_client.delete_points(
        visual_collection_name(knowledge_base.qdrant_collection),
        visual_point_ids,
    )
    await delete_generated_document_objects(request, document)
    reset_document = await reset_document_for_reprocess(
        session,
        document,
        actor=current_actor(current_user),
    )
    enqueue_document(reset_document.id)
    await clear_retrieval_cache(request)
    return DocumentResponse.model_validate(reset_document)
