"""Analysis history endpoints (search, filter, sort, paginate)."""

from __future__ import annotations

import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_analysis
from app.database.session import get_db
from app.models.analysis import AudioAnalysis
from app.models.user import User
from app.schemas.analysis import AnalysisOut, HistoryPage

router = APIRouter(prefix="/api/history", tags=["History"])

SORTABLE = {
    "created_at": AudioAnalysis.created_at,
    "filename": AudioAnalysis.filename,
    "model_score": AudioAnalysis.model_score,
    "audio_duration": AudioAnalysis.audio_duration,
}


@router.get("", response_model=HistoryPage, summary="List your analyses")
def list_history(
    q: str | None = Query(default=None, max_length=120, description="Filename search"),
    status_filter: str | None = Query(
        default=None, alias="status", pattern="^(pending|completed|unavailable|failed)$"
    ),
    prediction: str | None = Query(default=None, pattern="^(genuine|synthetic)$"),
    sort: str = Query(default="created_at", pattern="^(created_at|filename|model_score|audio_duration)$"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HistoryPage:
    filters = [AudioAnalysis.user_id == current_user.id]
    if q:
        term = f"%{q.strip().lower()}%"
        filters.append(func.lower(AudioAnalysis.filename).like(term))
    if status_filter:
        filters.append(AudioAnalysis.analysis_status == status_filter)
    if prediction:
        filters.append(AudioAnalysis.predicted_class == prediction)

    total = db.scalar(select(func.count()).select_from(AudioAnalysis).where(*filters)) or 0

    column = SORTABLE[sort]
    ordering = asc(column) if order == "asc" else desc(column)
    # Stable tiebreaker so pagination never repeats/skips rows.
    tiebreak = desc(AudioAnalysis.id) if order == "desc" else asc(AudioAnalysis.id)

    stmt = (
        select(AudioAnalysis)
        .where(*filters)
        .order_by(ordering, tiebreak)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(db.scalars(stmt).all())
    pages = max(1, math.ceil(total / page_size)) if total else 1
    return HistoryPage(
        items=[AnalysisOut.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/{analysis_id}", response_model=AnalysisOut, summary="History record detail")
def history_detail(
    analysis_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisOut:
    analysis = get_owned_analysis(db, current_user, analysis_id)
    return AnalysisOut.model_validate(analysis)
