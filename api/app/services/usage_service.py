from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.models.usage_daily import UsageDaily


async def list_usage_daily(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[UsageDaily]:
    """Return daily usage rows for a tenant within an optional date range."""

    statement = select(UsageDaily).where(UsageDaily.tenant_id == tenant_id)
    if start_date is not None:
        statement = statement.where(UsageDaily.date >= start_date)
    if end_date is not None:
        statement = statement.where(UsageDaily.date <= end_date)

    result = await session.execute(statement.order_by(UsageDaily.date.desc()))
    return list(result.scalars().all())
