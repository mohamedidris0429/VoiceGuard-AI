"""Phase 4 - near-real-time chunked analysis endpoints.

Every response states ``mode="near_real_time_chunked"`` and the latency caveat,
so a client can never present chunk scoring as continuous live monitoring.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.rate_limit import enforce
from app.database.session import get_db
from app.models.user import User
from app.schemas.stream import StreamSessionCreate, StreamSessionOut
from app.services import stream_service

router = APIRouter(prefix="/api/stream", tags=["Live analysis"])


@router.post(
    "/sessions",
    response_model=StreamSessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Start a near-real-time chunked session",
)
def create_session(
    payload: StreamSessionCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamSessionOut:
    enforce(request, "analysis", f"user:{current_user.id}")
    return StreamSessionOut(**stream_service.create_session(current_user.id, payload.chunk_seconds))


@router.post(
    "/sessions/{session_id}/chunks",
    response_model=StreamSessionOut,
    summary="Score one captured chunk and return the running result",
)
async def add_chunk(
    session_id: str,
    request: Request,
    file: UploadFile = File(..., description="One self-contained WAV/MP3 chunk"),
    chunk_index: int | None = Form(
        None, description="Optional zero-based index; rejected if it is out of order."
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamSessionOut:
    enforce(request, "analysis", f"user:{current_user.id}")
    payload = await stream_service.add_chunk(
        session_id, current_user.id, file, chunk_index=chunk_index
    )
    return StreamSessionOut(**payload)


@router.get(
    "/sessions/{session_id}",
    response_model=StreamSessionOut,
    summary="Current state of a live session",
)
def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamSessionOut:
    return StreamSessionOut(**stream_service.get_session(session_id, current_user.id))


@router.post(
    "/sessions/{session_id}/stop",
    response_model=StreamSessionOut,
    summary="Stop a live session and return its summary",
)
def stop_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamSessionOut:
    return StreamSessionOut(**stream_service.stop_session(session_id, current_user.id))


@router.delete(
    "/sessions/{session_id}",
    summary="Discard a live session immediately",
)
def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    stream_service.stop_session(session_id, current_user.id)
    stream_service.reset_session(session_id)
    return {"message": "Live session discarded.", "session_id": session_id}
