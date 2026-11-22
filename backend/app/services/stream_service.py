"""Phase 4 - near-real-time chunked analysis.

Design and honesty constraints
------------------------------
The browser records short, self-contained clips (default 3 s) one after another
and uploads each one as it is finalised. The server decodes the chunk, runs the
*same* pretrained detector used for whole-file analysis, and returns that
chunk's score immediately.

This is therefore **near-real-time**, not continuous live detection: latency is
at least one chunk length plus inference time, and there are small gaps while the
browser finalises the next clip. The API labels every response with
``mode="near_real_time_chunked"`` and a latency note.

Chunk audio is written to a temporary file only for the duration of decoding and
is deleted immediately afterwards. Nothing is persisted in the database, no
recording is retained, and results are capped in memory so a long session cannot
grow the process footprint.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from app.ai.detector import get_detector
from app.core.config import settings
from app.core.errors import AppError, ModelUnavailableError, ValidationAppError
from app.services import storage_service

MODE = "near_real_time_chunked"
MIN_CHUNK_SECONDS = 0.5
MAX_CHUNK_SECONDS = 10.0
MAX_CHUNKS_PER_SESSION = 40
MAX_ACTIVE_SESSIONS = 3
SESSION_TTL_SECONDS = 600.0
MAX_CHUNK_BYTES = 8 * 1024 * 1024
DECODE_RATE = 16000

LATENCY_NOTE = (
    "Chunks are scored after they are captured, one at a time. Latency is at least "
    "the chunk length plus model inference, with a short gap between chunks, so this "
    "is near-real-time analysis - not continuous or instantaneous monitoring."
)

STREAM_CAVEAT = (
    "Live chunk scores are independent model outputs for short windows. The running "
    "average is a summary of those windows only; it is not a verified whole-file "
    "verdict, and it is never stored as one. Chunk audio is discarded after scoring."
)


@dataclass
class _Chunk:
    index: int
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    score: float
    label: str
    peak: float
    latency_ms: int
    model_version: str


@dataclass
class _Session:
    id: str
    user_id: int
    chunk_seconds: float
    created_at: float
    updated_at: float
    status: str = "active"
    chunks: list[_Chunk] = field(default_factory=list)
    model_id: str = ""
    model_version: str = ""


_lock = threading.RLock()
_sessions: dict[str, _Session] = {}


def _now() -> float:
    return time.monotonic()


def _purge_expired() -> None:
    cutoff = _now() - SESSION_TTL_SECONDS
    for session_id, session in list(_sessions.items()):
        if session.updated_at < cutoff:
            _sessions.pop(session_id, None)


def _owned(session_id: str, user_id: int) -> _Session:
    with _lock:
        _purge_expired()
        session = _sessions.get(session_id)
    # Same response for unknown / expired / someone else's session.
    if session is None or session.user_id != user_id:
        raise AppError(
            "Live session not found or expired.", code="stream_session_not_found", status_code=404
        )
    return session


def _view(session: _Session) -> dict[str, Any]:
    scores = [chunk.score for chunk in session.chunks]
    return {
        "session_id": session.id,
        "status": session.status,
        "mode": MODE,
        "chunk_seconds": session.chunk_seconds,
        "created_at": datetime.fromtimestamp(
            time.time() - (_now() - session.created_at), tz=timezone.utc
        ),
        "total_chunks": len(session.chunks),
        "scored_chunks": len(scores),
        "duration_seconds": round(sum(chunk.duration_seconds for chunk in session.chunks), 3),
        "average_score": round(float(np.mean(scores)), 6) if scores else None,
        "chunks": [
            {
                "index": chunk.index,
                "start_seconds": chunk.start_seconds,
                "end_seconds": chunk.end_seconds,
                "duration_seconds": chunk.duration_seconds,
                "score": chunk.score,
                "label": chunk.label,
                "peak": chunk.peak,
                "latency_ms": chunk.latency_ms,
                "model_version": chunk.model_version,
            }
            for chunk in session.chunks
        ],
        "model_id": session.model_id or settings.model_id,
        "model_version": session.model_version or None,
        "window_note": (
            f"The detector scores up to {settings.model_max_windows} window(s) of "
            f"{settings.model_window_seconds:g}s per chunk and averages them; shorter "
            "chunks are zero-padded by the existing detector."
        ),
        "latency_note": LATENCY_NOTE,
        "caveat": STREAM_CAVEAT,
    }


def create_session(user_id: int, chunk_seconds: float = 3.0) -> dict[str, Any]:
    chunk = float(chunk_seconds)
    if not MIN_CHUNK_SECONDS <= chunk <= MAX_CHUNK_SECONDS:
        raise ValidationAppError(
            f"chunk_seconds must be between {MIN_CHUNK_SECONDS:g} and {MAX_CHUNK_SECONDS:g}."
        )

    with _lock:
        _purge_expired()
        active = sum(
            1 for session in _sessions.values() if session.user_id == user_id and session.status == "active"
        )
        if active >= MAX_ACTIVE_SESSIONS:
            raise AppError(
                f"You already have {MAX_ACTIVE_SESSIONS} active live sessions. Stop one first.",
                code="too_many_sessions",
                status_code=429,
            )
        session = _Session(
            id=uuid.uuid4().hex,
            user_id=user_id,
            chunk_seconds=round(chunk, 3),
            created_at=_now(),
            updated_at=_now(),
            model_id=settings.model_id,
        )
        _sessions[session.id] = session
    return _view(session)


def get_session(session_id: str, user_id: int) -> dict[str, Any]:
    session = _owned(session_id, user_id)
    with _lock:
        return _view(session)


def _decode_chunk(path: Path) -> np.ndarray:
    import librosa

    try:
        waveform, _ = librosa.load(
            str(path), sr=DECODE_RATE, mono=True, dtype="float32"
        )
    except Exception as exc:
        raise ValidationAppError(
            "This chunk could not be decoded as audio.", code="invalid_chunk"
        ) from exc

    if waveform.size == 0:
        raise ValidationAppError("The audio chunk contains no samples.", code="invalid_chunk")
    if not np.isfinite(waveform).all():
        raise ValidationAppError("The audio chunk contains invalid samples.", code="invalid_chunk")

    peak = float(np.max(np.abs(waveform)))
    if peak < 1e-4:
        raise ValidationAppError(
            "This chunk is silent, so there is nothing for the model to score.",
            code="silent_chunk",
        )
    return waveform


async def add_chunk(
    session_id: str,
    user_id: int,
    upload,
    *,
    chunk_index: int | None = None,
) -> dict[str, Any]:
    """Score one uploaded chunk and append it to the session (in order)."""
    session = _owned(session_id, user_id)
    with _lock:
        if session.status != "active":
            raise AppError(
                "This live session has been stopped.", code="stream_session_closed", status_code=409
            )
        expected = len(session.chunks)
        if chunk_index is not None and chunk_index != expected:
            raise AppError(
                f"Chunks must be uploaded in order (expected {expected}, received {chunk_index}).",
                code="chunk_out_of_order",
                status_code=409,
            )
        if expected >= MAX_CHUNKS_PER_SESSION:
            raise AppError(
                f"This session reached the {MAX_CHUNKS_PER_SESSION}-chunk limit. Stop it and start a new one.",
                code="stream_limit_reached",
                status_code=409,
            )

    stored = await storage_service.save_stream_chunk(upload, user_id)
    started = time.perf_counter()
    try:
        if stored.size > MAX_CHUNK_BYTES:  # defensive; storage already enforces limits
            raise ValidationAppError("This chunk is too large.", code="chunk_too_large")
        waveform = _decode_chunk(stored.path)
        duration = waveform.size / float(DECODE_RATE)
        if duration > session.chunk_seconds + 1.0:
            raise ValidationAppError(
                f"Chunk is {duration:.1f}s long but the session expects "
                f"{session.chunk_seconds:g}s chunks.",
                code="chunk_too_long",
            )
        if duration < MIN_CHUNK_SECONDS:
            raise ValidationAppError(
                f"Chunk is {duration:.2f}s; the minimum is {MIN_CHUNK_SECONDS:g}s.",
                code="chunk_too_short",
            )

        try:
            prediction = get_detector().predict(waveform, DECODE_RATE)
        except ModelUnavailableError as exc:
            raise AppError(exc.message, code="model_unavailable", status_code=503) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        with _lock:
            session = _owned(session_id, user_id)
            if session.status != "active":
                raise AppError(
                    "This live session was stopped while the chunk was being scored.",
                    code="stream_session_closed",
                    status_code=409,
                )
            index = len(session.chunks)
            start = round(index * session.chunk_seconds, 4)
            chunk = _Chunk(
                index=index,
                start_seconds=start,
                end_seconds=round(start + duration, 4),
                duration_seconds=round(duration, 3),
                score=round(float(prediction.synthetic_probability), 6),
                label=prediction.predicted_class,
                peak=round(float(np.max(np.abs(waveform))), 4),
                latency_ms=latency_ms,
                model_version=prediction.model_version,
            )
            session.chunks.append(chunk)
            session.updated_at = _now()
            session.model_version = prediction.model_version
            return _view(session)
    finally:
        # Chunk audio is never retained.
        stored.path.unlink(missing_ok=True)


def stop_session(session_id: str, user_id: int) -> dict[str, Any]:
    session = _owned(session_id, user_id)
    with _lock:
        if session.status == "active":
            session.status = "stopped"
            session.updated_at = _now()
        return _view(session)


def reset_session(session_id: str) -> None:
    """Drop one session from memory (used by DELETE)."""
    with _lock:
        _sessions.pop(session_id, None)


def reset_registry() -> None:
    """Test helper: drop all sessions."""
    with _lock:
        _sessions.clear()
