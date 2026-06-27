"""Auth routes — signup, login, and the current-user lookup.

Builds directly on the security seam (app/security.py):
  - hash_password / verify_password  — bcrypt
  - create_access_token(subject)     — JWT with `sub` = str(user.id)
  - get_current_user(...)            — dependency that loads the User

Two login paths are intentionally exposed:
  - POST /auth/login       — form-encoded (OAuth2PasswordRequestForm) so the
                             Swagger "Authorize" button works out of the box.
  - POST /auth/login-json  — JSON body (UserLogin) for the Streamlit client,
                             which posts application/json.
Both return an identical Token. The frontend should call /auth/login-json.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import Token, UserCreate, UserLogin, UserOut
from app.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _normalize_email(email: str) -> str:
    """Emails are case-insensitive in practice; store + compare lower-cased."""
    return email.strip().lower()


def _issue_token(user: User) -> Token:
    """Sign a token whose subject is the user's id (consumed by get_current_user)."""
    return Token(access_token=create_access_token(user.id))


@router.post(
    "/signup",
    response_model=Token,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account and return an access token",
)
def signup(body: UserCreate, db: Session = Depends(get_db)) -> Token:
    email = _normalize_email(body.email)

    existing = db.query(User).filter(User.email == email).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That email is already registered.",
        )

    user = User(
        email=email,
        hashed_password=hash_password(body.password),
        name=body.name.strip(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return _issue_token(user)


@router.post(
    "/login",
    response_model=Token,
    summary="Form login (OAuth2) — powers Swagger's Authorize button",
)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    """OAuth2 password flow. `username` carries the email; `password` the secret."""
    email = _normalize_email(form_data.username)
    user = db.query(User).filter(User.email == email).first()

    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _issue_token(user)


@router.post(
    "/login-json",
    response_model=Token,
    summary="JSON login for the Streamlit frontend",
)
def login_json(body: UserLogin, db: Session = Depends(get_db)) -> Token:
    """Same credential check as /login, but accepts an application/json body."""
    email = _normalize_email(body.email)
    user = db.query(User).filter(User.email == email).first()

    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _issue_token(user)


@router.get(
    "/me",
    response_model=UserOut,
    summary="Return the authenticated user's profile",
)
def me(current_user: User = Depends(get_current_user)) -> User:
    """Echo back the current user (also a cheap token-validity probe)."""
    return current_user
