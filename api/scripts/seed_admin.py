from __future__ import annotations

import asyncio
import os
import sys
from secrets import token_urlsafe

from sqlalchemy import inspect, select
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from api.app.config import Settings
from api.app.core.security import hash_password
from api.app.db.session import create_engine, create_session_factory
from api.app.models.tenant import Tenant
from api.app.models.user import User

DEFAULT_ADMIN_EMAIL = "admin@example.com"
DEFAULT_TENANT_NAME = "Default Tenant"
MIN_PASSWORD_LENGTH = 12
REQUIRED_TABLES = {"tenants", "users"}


class SeedAdminError(Exception):
    """Raised for expected bootstrap failures with actionable messages."""


def env_bool(name: str, default: bool = False) -> bool:
    """Read a boolean environment variable."""

    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "y", "on"}


def get_admin_password() -> tuple[str, bool]:
    """Return the requested admin password and whether it was generated."""

    password = os.getenv("BYOB_ADMIN_PASSWORD")
    if password is None:
        return token_urlsafe(24), True
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"BYOB_ADMIN_PASSWORD must be at least {MIN_PASSWORD_LENGTH} characters."
        )
    return password, False


async def get_or_create_tenant(session: AsyncSession, tenant_name: str) -> Tenant:
    """Return an existing tenant by name or create one."""

    tenant = await session.scalar(select(Tenant).where(Tenant.name == tenant_name))
    if tenant is not None:
        return tenant

    tenant = Tenant(name=tenant_name)
    session.add(tenant)
    await session.flush()
    return tenant


async def schema_has_required_tables(engine: AsyncEngine) -> bool:
    """Return whether Alembic has created the tables needed by this script."""

    def get_table_names(connection: Connection) -> set[str]:
        return set(inspect(connection).get_table_names())

    async with engine.connect() as connection:
        table_names = await connection.run_sync(get_table_names)
    return REQUIRED_TABLES.issubset(table_names)


async def seed_admin() -> None:
    """Create the first tenant admin account if it does not exist."""

    admin_email = os.getenv("BYOB_ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL).strip().lower()
    tenant_name = os.getenv("BYOB_TENANT_NAME", DEFAULT_TENANT_NAME).strip()
    reset_password = env_bool("BYOB_ADMIN_RESET_PASSWORD")
    password, generated_password = get_admin_password()

    settings = Settings()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)

    try:
        if not await schema_has_required_tables(engine):
            raise SeedAdminError(
                "Database schema is missing required tables. "
                "Run `uv run alembic upgrade head` before seeding the admin user."
            )

        async with session_factory() as session:
            tenant = await get_or_create_tenant(session, tenant_name)
            user = await session.scalar(select(User).where(User.email == admin_email))

            if user is None:
                user = User(
                    tenant_id=tenant.id,
                    email=admin_email,
                    password_hash=hash_password(password),
                    role="admin",
                )
                session.add(user)
                action = "created"
            elif reset_password:
                user.password_hash = hash_password(password)
                user.role = "admin"
                action = "updated"
            else:
                action = "exists"

            await session.commit()
    finally:
        await engine.dispose()

    print(f"Admin user {action}: {admin_email}")
    print(f"Tenant: {tenant_name}")
    if action == "exists":
        print("Password unchanged. Set BYOB_ADMIN_RESET_PASSWORD=true to reset it.")
    elif generated_password:
        print(f"Generated password: {password}")
        print("Store this password now; it will not be shown again.")
    else:
        print("Password loaded from BYOB_ADMIN_PASSWORD.")


def main() -> None:
    try:
        asyncio.run(seed_admin())
    except (SeedAdminError, ValueError) as exc:
        print(f"seed_admin failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
