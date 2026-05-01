from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.app.deps import get_current_user
from api.app.schemas.agent import AgentAskRequest, AgentAskResponse
from api.app.schemas.auth import CurrentUser
from api.app.services.agent_service import (
    AgentMcpUnavailableError,
    AgentServiceError,
    answer_with_mcp_agent,
)

router = APIRouter(prefix="/agent", tags=["agent"])
CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


@router.post("/ask", response_model=AgentAskResponse)
async def ask_agent_endpoint(
    payload: AgentAskRequest,
    request: Request,
    current_user: CurrentUserDep,
) -> AgentAskResponse:
    """Ask the simple MCP-backed QA Agent a question."""

    try:
        return await answer_with_mcp_agent(
            request.app.state.settings,
            request_id=request.state.request_id,
            payload=payload,
        )
    except AgentMcpUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except AgentServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
