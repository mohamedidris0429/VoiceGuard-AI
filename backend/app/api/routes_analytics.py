"""Analytics endpoints computed from the user's stored analyses."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.analysis import (
    STATUS_COMPLETED,
    STATUS_PENDING,
    STATUS_UNAVAILABLE,
    AudioAnalysis,
)
from app.models.user import User
from app.schemas.analytics import BucketCount, SummaryOut, TrendPoint, TrendsOut

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


@router.get("/summary", response_model=SummaryOut, summary="Aggregate statistics")
def summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SummaryOut:
    base = select(
        func.count(AudioAnalysis.id),
        func.coalesce(func.sum(case((AudioAnalysis.predicted_class == "genuine", 1), else_=0)), 0),
        func.coalesce(func.sum(case((AudioAnalysis.predicted_class == "synthetic", 1), else_=0)), 0),
        func.coalesce(func.sum(case((AudioAnalysis.analysis_status == STATUS_UNAVAILABLE, 1), else_=0)), 0),
        func.coalesce(func.sum(case((AudioAnalysis.analysis_status == STATUS_PENDING, 1), else_=0)), 0),
        func.coalesce(func.sum(case((AudioAnalysis.analysis_status == "failed", 1), else_=0)), 0),
        func.avg(case((AudioAnalysis.analysis_status == STATUS_COMPLETED, AudioAnalysis.model_score))),
        func.avg(AudioAnalysis.audio_duration),
        func.sum(AudioAnalysis.audio_duration),
        func.max(AudioAnalysis.created_at),
        func.min(AudioAnalysis.created_at),
    ).where(AudioAnalysis.user_id == current_user.id)

    row = db.execute(base).one()
    last_successful = db.scalar(
        select(func.max(AudioAnalysis.created_at)).where(
            AudioAnalysis.user_id == current_user.id,
            AudioAnalysis.analysis_status == STATUS_COMPLETED,
        )
    )

    return SummaryOut(
        total_analyses=int(row[0] or 0),
        genuine=int(row[1] or 0),
        synthetic=int(row[2] or 0),
        unavailable=int(row[3] or 0),
        pending=int(row[4] or 0),
        failed=int(row[5] or 0),
        average_confidence=round(float(row[6]), 4) if row[6] is not None else None,
        average_duration=round(float(row[7]), 2) if row[7] is not None else None,
        total_audio_seconds=round(float(row[8]), 1) if row[8] is not None else None,
        last_analysis_at=row[9],
        first_analysis_at=row[10],
        last_successful_at=last_successful,
    )


@router.get("/trends", response_model=TrendsOut, summary="Time series and distributions")
def trends(
    days: int = Query(default=14, ge=7, le=90),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TrendsOut:
    today = datetime.now(timezone.utc).date()
    since_date = today - timedelta(days=days - 1)
    since = datetime.combine(since_date, datetime.min.time(), tzinfo=timezone.utc)

    day = func.date(AudioAnalysis.created_at)
    daily_rows = db.execute(
        select(
            day.label("day"),
            AudioAnalysis.predicted_class,
            func.count(AudioAnalysis.id),
        )
        .where(AudioAnalysis.user_id == current_user.id, AudioAnalysis.created_at >= since)
        .group_by(day, AudioAnalysis.predicted_class)
    ).all()

    buckets: dict[str, dict[str, int]] = {}
    for day_value, predicted_class, count in daily_rows:
        key = str(day_value)
        entry = buckets.setdefault(key, {"total": 0, "genuine": 0, "synthetic": 0, "other": 0})
        entry["total"] += int(count)
        if predicted_class == "genuine":
            entry["genuine"] += int(count)
        elif predicted_class == "synthetic":
            entry["synthetic"] += int(count)
        else:
            entry["other"] += int(count)

    daily: list[TrendPoint] = []
    for offset in range(days):
        current = since_date + timedelta(days=offset)
        key = current.isoformat()
        entry = buckets.get(key, {"total": 0, "genuine": 0, "synthetic": 0, "other": 0})
        daily.append(TrendPoint(date=key, **entry))

    confidence_ranges = [
        ("0-20%", 0.0, 0.2),
        ("20-40%", 0.2, 0.4),
        ("40-60%", 0.4, 0.6),
        ("60-80%", 0.6, 0.8),
        ("80-100%", 0.8, 1.0001),
    ]
    completed_filters = (
        AudioAnalysis.user_id == current_user.id,
        AudioAnalysis.analysis_status == STATUS_COMPLETED,
    )
    confidence_buckets: list[BucketCount] = []
    for label, low, high in confidence_ranges:
        count = db.scalar(
            select(func.count(AudioAnalysis.id)).where(
                *completed_filters,
                AudioAnalysis.model_score >= low,
                AudioAnalysis.model_score < high,
            )
        )
        confidence_buckets.append(BucketCount(label=label, count=int(count or 0)))

    duration_ranges = [
        ("< 5 s", 0.0, 5.0),
        ("5-15 s", 5.0, 15.0),
        ("15-30 s", 15.0, 30.0),
        ("30-45 s", 30.0, 45.0),
        ("45 s +", 45.0, 1e6),
    ]
    duration_buckets: list[BucketCount] = []
    for label, low, high in duration_ranges:
        count = db.scalar(
            select(func.count(AudioAnalysis.id)).where(
                AudioAnalysis.user_id == current_user.id,
                AudioAnalysis.audio_duration.is_not(None),
                AudioAnalysis.audio_duration >= low,
                AudioAnalysis.audio_duration < high,
            )
        )
        duration_buckets.append(BucketCount(label=label, count=int(count or 0)))

    status_rows = db.execute(
        select(AudioAnalysis.analysis_status, func.count(AudioAnalysis.id))
        .where(AudioAnalysis.user_id == current_user.id)
        .group_by(AudioAnalysis.analysis_status)
    ).all()
    status_breakdown = [
        BucketCount(label=str(status_value), count=int(count)) for status_value, count in status_rows
    ]

    return TrendsOut(
        range_days=days,
        daily=daily,
        confidence_buckets=confidence_buckets,
        duration_buckets=duration_buckets,
        status_breakdown=status_breakdown,
    )
