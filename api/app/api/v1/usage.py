from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.deps import get_current_user, get_db_session
from api.app.schemas.auth import CurrentUser, UsageDailyResponse, UsageResponse
from api.app.services.usage_service import list_usage_daily

router = APIRouter(prefix="/usage", tags=["usage"])
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
OptionalDateQuery = Annotated[date | None, Query()]


@router.get("", response_model=UsageResponse)
async def get_usage(
    request: Request,
    current_user: CurrentUserDep,
    session: DbSession,
    start_date: OptionalDateQuery = None,
    end_date: OptionalDateQuery = None,
) -> UsageResponse:
    """Return daily usage aggregates for the current tenant."""

    rows = await list_usage_daily(
        session,
        current_user.tenant_id,
        start_date=start_date,
        end_date=end_date,
    )
    return UsageResponse(
        request_id=request.state.request_id,
        tenant_id=current_user.tenant_id,
        data=[UsageDailyResponse.model_validate(row) for row in rows],
    )
