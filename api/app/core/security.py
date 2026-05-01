from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from api.app.config import Settings

_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Hash a plaintext password for management console users."""

    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Return whether a plaintext password matches the stored hash."""

    return _password_hash.verify(password, password_hash)


def create_access_token(
    settings: Settings,
    *,
    user_id: UUID,
    role: str,
    email: str,
) -> str:
    """Create a signed JWT for management console access."""

    expires_at = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "role": role,
        "email": email,
        "exp": expires_at,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(settings: Settings, token: str) -> dict[str, object]:
    """Decode and validate a management JWT."""

    return jwt.decode(
        token,
        settings.jwt_secret_key.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
    )
