from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.deps import get_current_user, get_db_session
from api.app.schemas.auth import CurrentUser
from api.app.schemas.document import (
    ChunkListResponse,
    ChunkResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentTextCreateRequest,
    DocumentUrlCreateRequest,
)
from api.app.services.document_service import (
    create_file_document,
    create_text_document,
    create_url_document,
    delete_document,
    get_document,
    hash_content,
    list_chunks,
    list_documents,
    reset_document_for_reprocess,
)
from api.app.services.knowledge_base_service import get_knowledge_base
from workers.tasks.document_tasks import process_document

router = APIRouter(tags=["documents"])
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
UploadFileField = Annotated[UploadFile, File()]


def enqueue_document(document_id: UUID) -> None:
    """Queue asynchronous document processing."""

    process_document.delay(str(document_id))


@router.post(
    "/knowledge-bases/{kb_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document_endpoint(
    kb_id: UUID,
    request: Request,
    current_user: CurrentUserDep,
    session: DbSession,
    file: UploadFileField,
) -> DocumentResponse:
    """Upload a file document and enqueue ingestion."""

    knowledge_base = await get_knowledge_base(session, current_user.tenant_id, kb_id)
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
    object_key = f"tenants/{current_user.tenant_id}/knowledge_bases/{kb_id}/{hash_content(content)}"
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
        file_hash=hash_content(content),
    )
    enqueue_document(document.id)
    return DocumentResponse.model_validate(document)


@router.post(
    "/knowledge-bases/{kb_id}/documents/text",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_text_document_endpoint(
    kb_id: UUID,
    payload: DocumentTextCreateRequest,
    current_user: CurrentUserDep,
    session: DbSession,
) -> DocumentResponse:
    """Create a document from direct text input and enqueue ingestion."""

    knowledge_base = await get_knowledge_base(session, current_user.tenant_id, kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    document = await create_text_document(session, knowledge_base, payload)
    enqueue_document(document.id)
    return DocumentResponse.model_validate(document)


@router.post(
    "/knowledge-bases/{kb_id}/documents/url",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_url_document_endpoint(
    kb_id: UUID,
    payload: DocumentUrlCreateRequest,
    current_user: CurrentUserDep,
    session: DbSession,
) -> DocumentResponse:
    """Create a document from a URL and enqueue ingestion."""

    knowledge_base = await get_knowledge_base(session, current_user.tenant_id, kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    document = await create_url_document(session, knowledge_base, payload)
    enqueue_document(document.id)
    return DocumentResponse.model_validate(document)


@router.get("/knowledge-bases/{kb_id}/documents", response_model=DocumentListResponse)
async def list_documents_endpoint(
    kb_id: UUID,
    request: Request,
    current_user: CurrentUserDep,
    session: DbSession,
) -> DocumentListResponse:
    """List documents in a knowledge base."""

    knowledge_base = await get_knowledge_base(session, current_user.tenant_id, kb_id)
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
    """Return document details for the current tenant."""

    document = await get_document(session, current_user.tenant_id, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return DocumentResponse.model_validate(document)


@router.get("/documents/{document_id}/chunks", response_model=ChunkListResponse)
async def list_chunks_endpoint(
    document_id: UUID,
    request: Request,
    current_user: CurrentUserDep,
    session: DbSession,
) -> ChunkListResponse:
    """List persisted chunks for one document."""

    document = await get_document(session, current_user.tenant_id, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    chunks = await list_chunks(session, document)
    return ChunkListResponse(
        request_id=request.state.request_id,
        data=[ChunkResponse.model_validate(chunk) for chunk in chunks],
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document_endpoint(
    document_id: UUID,
    current_user: CurrentUserDep,
    session: DbSession,
) -> None:
    """Delete a document and its chunks."""

    document = await get_document(session, current_user.tenant_id, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    await delete_document(session, document)


@router.post("/documents/{document_id}/reprocess", response_model=DocumentResponse)
async def reprocess_document_endpoint(
    document_id: UUID,
    current_user: CurrentUserDep,
    session: DbSession,
) -> DocumentResponse:
    """Reset a document and enqueue ingestion again."""

    document = await get_document(session, current_user.tenant_id, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    reset_document = await reset_document_for_reprocess(session, document)
    enqueue_document(reset_document.id)
    return DocumentResponse.model_validate(reset_document)
