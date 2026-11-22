"""Shared API dependencies: bearer auth, current user, ownership checks."""

from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AuthError, NotFoundError
from app.core.security import TokenError, decode_access_token
from app.database.session import get_db
from app.models.analysis import AudioAnalysis
from app.models.user import User

bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Paste the access token returned by POST /api/auth/login.",
)


def _user_from_credentials(
    credentials: HTTPAuthorizationCredentials | None, db: Session
) -> User | None:
    if credentials is None or not credentials.credentials:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise AuthError(str(exc)) from exc
    try:
        user_id = int(payload.get("sub", ""))
    except (TypeError, ValueError) as exc:
        raise AuthError("Invalid authentication token.") from exc
    user = db.get(User, user_id)
    if user is None:
        raise AuthError("This account no longer exists.")
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    user = _user_from_credentials(credentials, db)
    if user is None:
        raise AuthError("Authentication required.")
    return user


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    try:
        return _user_from_credentials(credentials, db)
    except AuthError:
        return None


def get_owned_analysis(db: Session, user: User, analysis_id: int) -> AudioAnalysis:
    """Fetch an analysis only if it belongs to the requesting user."""
    analysis = db.get(AudioAnalysis, analysis_id)
    if analysis is None or analysis.user_id != user.id:
        # Same response for "missing" and "someone else's" -> no record enumeration.
        raise NotFoundError("Analysis not found.")
    return analysis
