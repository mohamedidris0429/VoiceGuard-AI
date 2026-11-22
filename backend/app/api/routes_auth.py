"""Authentication and profile endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.errors import AppError, AuthError
from app.core.rate_limit import enforce
from app.core.security import create_access_token, hash_password, verify_password
from app.database.session import get_db
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    MessageResponse,
    TokenResponse,
    UserLogin,
    UserOut,
    UserRegister,
    UserUpdate,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id),
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserOut.model_validate(user),
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new account",
)
def register(
    payload: UserRegister,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    enforce(request, "auth")
    existing = db.scalar(select(User).where(func.lower(User.email) == payload.email))
    if existing is not None:
        raise AppError(
            "An account with this email already exists.",
            code="email_taken",
            status_code=status.HTTP_409_CONFLICT,
        )

    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        preferences={"email_notifications": False, "default_view": "dashboard"},
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _token_response(user)


@router.post("/login", response_model=TokenResponse, summary="Sign in and receive a JWT")
def login(payload: UserLogin, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    enforce(request, "auth")
    user = db.scalar(select(User).where(func.lower(User.email) == payload.email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise AuthError("Invalid email or password.")
    return _token_response(user)


@router.get("/me", response_model=UserOut, summary="Current authenticated user")
def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)


@router.patch("/me", response_model=UserOut, summary="Update profile details")
def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserOut:
    if payload.name is not None:
        current_user.name = payload.name
    if payload.preferences is not None:
        allowed_keys = {"email_notifications", "default_view", "compact_tables", "theme"}
        current_user.preferences = {
            key: value for key, value in payload.preferences.items() if key in allowed_keys
        }
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return UserOut.model_validate(current_user)


@router.post(
    "/change-password",
    response_model=MessageResponse,
    summary="Change the account password",
)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    enforce(request, "auth")
    if not verify_password(payload.current_password, current_user.password_hash):
        raise AuthError("Your current password is incorrect.")
    if verify_password(payload.new_password, current_user.password_hash):
        raise AppError(
            "The new password must be different from the current password.",
            code="password_unchanged",
        )
    current_user.password_hash = hash_password(payload.new_password)
    db.add(current_user)
    db.commit()
    return MessageResponse(message="Password updated successfully.")
