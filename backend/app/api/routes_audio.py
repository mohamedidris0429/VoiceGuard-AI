"""Audio upload, analysis, media and comparison endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_analysis
from app.core.config import settings
from app.core.errors import AppError
from app.core.rate_limit import enforce
from app.database.session import get_db
from app.models.analysis import STATUS_COMPLETED, AudioAnalysis
from app.models.user import User
from app.schemas.analysis import (
    AnalysisOut,
    AnalyzeRequest,
    ComparisonOut,
    DeleteResult,
    WaveformOut,
)
from app.services import analysis_service, audio_service, storage_service

logger = logging.getLogger("voiceguard.audio")

router = APIRouter(prefix="/api/audio", tags=["Audio"])

DISCLAIMER = (
    "AI voice detection is not 100% reliable. Results should be treated as indicators, "
    "not conclusive evidence. Two recordings are analysed independently; no speaker "
    "verification is performed and no claim is made that they belong to the same person."
)


@router.post(
    "/upload",
    response_model=AnalysisOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a WAV or MP3 file for analysis",
)
async def upload_audio(
    request: Request,
    file: UploadFile = File(..., description="WAV or MP3 audio file"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisOut:
    enforce(request, "analysis", f"user:{current_user.id}")
    stored = await storage_service.save_upload(file, current_user.id)
    try:
        analysis = analysis_service.create_analysis(db, current_user, stored)
    except Exception:
        storage_service.delete_stored_file(stored.reference)
        raise
    return AnalysisOut.model_validate(analysis)


@router.post(
    "/analyze",
    response_model=AnalysisOut,
    summary="Run AI inference on an uploaded file",
)
def analyze_audio(
    payload: AnalyzeRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisOut:
    enforce(request, "analysis", f"user:{current_user.id}")
    analysis = get_owned_analysis(db, current_user, payload.analysis_id)
    if analysis.analysis_status == STATUS_COMPLETED:
        return AnalysisOut.model_validate(analysis)
    analysis = analysis_service.run_analysis(db, analysis)
    return AnalysisOut.model_validate(analysis)


@router.post(
    "/compare",
    response_model=ComparisonOut,
    summary="Analyse two recordings separately and compare their results",
)
async def compare_audio(
    request: Request,
    file_a: UploadFile = File(...),
    file_b: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ComparisonOut:
    enforce(request, "analysis", f"user:{current_user.id}")
    stored_left = await storage_service.save_upload(file_a, current_user.id)
    try:
        left = analysis_service.create_analysis(db, current_user, stored_left, source="comparison")
    except Exception:
        storage_service.delete_stored_file(stored_left.reference)
        raise

    stored_right = await storage_service.save_upload(file_b, current_user.id)
    try:
        right = analysis_service.create_analysis(db, current_user, stored_right, source="comparison")
    except Exception:
        storage_service.delete_stored_file(stored_right.reference)
        raise

    left = analysis_service.run_analysis(db, left)
    right = analysis_service.run_analysis(db, right)

    duration_delta = None
    if left.audio_duration is not None and right.audio_duration is not None:
        duration_delta = round(left.audio_duration - right.audio_duration, 3)
    score_delta = None
    if left.model_score is not None and right.model_score is not None:
        score_delta = round(left.model_score - right.model_score, 6)

    return ComparisonOut(
        left=AnalysisOut.model_validate(left),
        right=AnalysisOut.model_validate(right),
        duration_delta_seconds=duration_delta,
        score_delta=score_delta,
        disclaimer=DISCLAIMER,
    )


@router.get("/{analysis_id}", response_model=AnalysisOut, summary="Analysis detail")
def get_analysis(
    analysis_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisOut:
    analysis = get_owned_analysis(db, current_user, analysis_id)
    return AnalysisOut.model_validate(analysis)


@router.get("/{analysis_id}/waveform", response_model=WaveformOut, summary="Waveform peaks")
def get_waveform(
    analysis_id: int,
    buckets: int = 800,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WaveformOut:
    analysis = get_owned_analysis(db, current_user, analysis_id)
    path = storage_service.audio_path_for(analysis.stored_file_reference)
    if not path.exists():
        raise AppError("The stored audio file is no longer available.", code="file_missing", status_code=410)
    data = audio_service.waveform_peaks(path, buckets=buckets)
    return WaveformOut(**data)


@router.get("/{analysis_id}/spectrogram", summary="Spectrogram PNG")
def get_spectrogram(
    analysis_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    analysis = get_owned_analysis(db, current_user, analysis_id)
    path = storage_service.audio_path_for(analysis.stored_file_reference)
    if not path.exists():
        raise AppError("The stored audio file is no longer available.", code="file_missing", status_code=410)
    png = audio_service.spectrogram_png(path)
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.delete("/{analysis_id}", response_model=DeleteResult, summary="Delete an analysis")
def delete_analysis(
    analysis_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DeleteResult:
    analysis = get_owned_analysis(db, current_user, analysis_id)
    reference = analysis.stored_file_reference
    db.delete(analysis)
    db.commit()
    storage_service.delete_stored_file(reference)
    return DeleteResult(message="Analysis deleted.", id=analysis_id)


@router.get("/limits/info", summary="Upload constraints", include_in_schema=True)
def upload_limits() -> dict:
    return {
        "max_upload_mb": settings.max_upload_mb,
        "allowed_formats": sorted(storage_service.ALLOWED_EXTENSIONS),
        "min_duration_seconds": settings.min_audio_seconds,
        "max_duration_seconds": settings.max_audio_seconds,
    }
