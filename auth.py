import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
import bcrypt
import jwt
from jwt import InvalidTokenError

# Load variables from .env before reading SECRET_KEY
load_dotenv()

SECRET_KEY = os.getenv("AQUAINTEL_SECRET_KEY", "")

ALGORITHM = "HS256"

ACCESS_TOKEN_MINUTES = int(
    os.getenv("AQUAINTEL_ACCESS_TOKEN_MINUTES", "60")
)

if not SECRET_KEY or len(SECRET_KEY) < 32:
    raise RuntimeError(
        "AQUAINTEL_SECRET_KEY must be set and contain at least 32 characters."
    )


def _password_bytes(password: str) -> bytes:
    if not isinstance(password, str):
        raise ValueError("Password must be a string")

    raw = password.encode("utf-8")

    if len(raw) > 72:
        raise ValueError("Password must be at most 72 UTF-8 bytes")

    return raw


def hash_password(password: str) -> str:
    raw = _password_bytes(password)
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            _password_bytes(plain_password),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def create_access_token(email: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_MINUTES
    )

    payload = {
        "sub": email,
        "role": role,
        "exp": expire,
    }

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decode_token(token: str):
    try:
        return jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )
    except InvalidTokenError:
        return None