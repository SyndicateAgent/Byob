from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import choice
from string import ascii_letters, digits
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from api.app.config import Settings

API_KEY_PREFIXES = ("kb_live_", "kb_test_")
_API_KEY_ALPHABET = ascii_letters + digits
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
    tenant_id: UUID,
    role: str,
    email: str,
) -> str:
    """Create a signed JWT for management console access."""

    expires_at = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
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


def generate_api_key(environment: str = "live") -> str:
    """Generate an API key returned only once to the caller."""

    prefix = "kb_test_" if environment == "test" else "kb_live_"
    suffix = "".join(choice(_API_KEY_ALPHABET) for _ in range(32))
    return f"{prefix}{suffix}"


def hash_api_key(api_key: str) -> str:
    """Return the stable SHA256 hash stored for API key authentication."""

    return sha256(api_key.encode("utf-8")).hexdigest()


def validate_api_key_format(api_key: str) -> bool:
    """Return whether an API key has the expected public format."""

    return any(api_key.startswith(prefix) for prefix in API_KEY_PREFIXES) and len(api_key) == 40
