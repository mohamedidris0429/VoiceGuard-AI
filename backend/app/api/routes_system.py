"""System health and AI model status endpoints."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.ai.detector import get_detector
from app.api.deps import get_optional_user
from app.core.config import settings
from app.database.session import SessionLocal, get_db
from app.models.analysis import STATUS_COMPLETED, AudioAnalysis
from app.models.user import User
from app.schemas.analytics import HealthOut, ModelStatusOut

logger = logging.getLogger("voiceguard.system")

router = APIRouter(prefix="/api", tags=["System"])

STARTED_AT = time.monotonic()


def _database_ok() -> bool:
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # pragma: no cover - reported, not raised
        logger.warning("Database health check failed: %s", exc.__class__.__name__)
        return False


@router.get("/health", response_model=HealthOut, summary="API, database and model health")
def health(
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> HealthOut:
    database_ok = _database_ok()
    model_status = get_detector().status()

    last_successful = None
    if current_user is not None:
        last_successful = db.scalar(
            select(func.max(AudioAnalysis.created_at)).where(
                AudioAnalysis.user_id == current_user.id,
                AudioAnalysis.analysis_status == STATUS_COMPLETED,
            )
        )

    healthy = database_ok
    return HealthOut(
        status="operational" if healthy else "degraded",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        database="connected" if database_ok else "unavailable",
        model_available=bool(model_status["available"]),
        uptime_seconds=int(time.monotonic() - STARTED_AT),
        timestamp=datetime.now(timezone.utc),
        last_successful_analysis_at=last_successful,
    )


@router.get("/model/status", response_model=ModelStatusOut, summary="AI model availability")
def model_status(
    load: bool = Query(
        default=False,
        description="Attempt to load the model now instead of waiting for the first analysis.",
    ),
) -> ModelStatusOut:
    status = get_detector().status(probe=load)
    detail = status.get("detail")
    if not status["loaded"]:
        detail = detail or (
            "The model loads on the first analysis. Use ?load=true to preload it now."
        )
    return ModelStatusOut(
        available=bool(status["available"]),
        loaded=bool(status["loaded"]),
        model_id=str(status["model_id"]),
        model_version=str(status["model_version"]),
        device=str(status["device"]),
        sample_rate=int(status["sample_rate"]),
        labels={str(k): str(v) for k, v in status["labels"].items()},
        window_seconds=float(status["window_seconds"]),
        max_windows=int(status["max_windows"]),
        threshold=float(status["threshold"]),
        parameters=status.get("parameters"),
        detail=detail,
    )
