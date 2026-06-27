"""Auth primitives: password hashing, JWT issue/decode, current-user dependency.

Seam contract (every route builds on this):
  - hash_password / verify_password  — bcrypt via passlib
  - create_access_token(subject)     — signs a JWT with `sub` = str(subject)
  - oauth2_scheme                    — OAuth2PasswordBearer(tokenUrl="auth/login")
  - get_current_user(...)            — decodes token, loads User by id, 401 on fail

JWT `sub` is always str(user.id). Routes must scope every query by
current_user.id — never trust a client-supplied user id.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User

# bcrypt has a 72-byte input limit; passlib truncates, but we keep the default
# rounds for speed on free-tier hardware.
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# tokenUrl is relative to the app root; matches the auth router's POST /auth/login.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

_credentials_exc = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


# ---------- passwords ----------
def hash_password(password: str) -> str:
    """Return a bcrypt hash of the plaintext password."""
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Constant-time check of a plaintext password against its bcrypt hash."""
    try:
        return _pwd_context.verify(plain_password, hashed_password)
    except ValueError:
        # Malformed/empty hash — treat as a failed verification, never raise.
        return False


# ---------- JWT ----------
def create_access_token(
    subject: str | int,
    expires_delta: timedelta | None = None,
) -> str:
    """Sign a JWT whose `sub` claim is str(subject) (the user id)."""
    expire = datetime.now(timezone.utc) + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode = {"sub": str(subject), "exp": expire}
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Decode the bearer token, load the User by id, or raise 401."""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        subject = payload.get("sub")
        if subject is None:
            raise _credentials_exc
        user_id = int(subject)
    except (JWTError, ValueError, TypeError):
        raise _credentials_exc

    user = db.get(User, user_id)
    if user is None:
        raise _credentials_exc
    return user
