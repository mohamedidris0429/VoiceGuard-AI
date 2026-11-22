"""Audio forensics workspace endpoints (Phase 1).

All data returned here is derived from the uploaded file and from the model
output already stored for the analysis. No new prediction is invented and no
visualisation is presented as verified forensic evidence.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_analysis
from app.core.config import settings
from app.core.errors import AppError, ValidationAppError
from app.core.rate_limit import enforce
from app.database.session import get_db
from app.models.user import User
from app.schemas.forensics import (
    ForensicsAudioOut,
    ForensicsModelOut,
    ForensicsOut,
    ForensicsSignalOut,
    ForensicsWaveformOut,
    SegmentSignalOut,
)
from app.schemas.segments import (
    SegmentAggregateOut,
    SegmentOut,
    SegmentsOut,
)
from app.services import audio_service, forensic_service, segment_service, storage_service

router = APIRouter(prefix="/api/forensics", tags=["Forensics"])

WAVEFORM_BUCKETS = 600

EVIDENCE_NOTE = (
    "Waveform, spectrogram and frequency charts are computed from the uploaded file. "
    "They are signal visualisations, not verified forensic evidence of authenticity or identity."
)

DISCLAIMER = (
    "Audio forensics here shows measured signal characteristics only. A model score is a "
    "probabilistic indicator and must not be treated as proof that a recording is cloned or genuine."
)

MEDIA_TYPES = {"wav": "audio/wav", "mp3": "audio/mpeg"}

BIT_DEPTHS = {
    "PCM_16": 16,
    "PCM_24": 24,
    "PCM_32": 32,
    "PCM_U8": 8,
    "FLOAT": 32,
    "DOUBLE": 64,
}

SEGMENTS_NOT_COMPUTED = (
    "No segment analysis is stored for this recording yet. "
    "POST to this endpoint to score the windows."
)


def _resolve_audio(analysis) -> Path:
    path = storage_service.audio_path_for(analysis.stored_file_reference)
    if not path.exists():
        raise AppError(
            "The stored audio file is no longer available.",
            code="file_missing",
            status_code=410,
        )
    return path


@router.get(
    "/{analysis_id}",
    response_model=ForensicsOut,
    summary="Forensic inspection of a stored analysis",
)
def get_forensics(
    analysis_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ForensicsOut:
    analysis = get_owned_analysis(db, current_user, analysis_id)
    path = _resolve_audio(analysis)

    try:
        info = audio_service.probe_audio(path)
    except audio_service.AudioProcessingError as exc:
        raise AppError(str(exc.message), code="audio_unreadable", status_code=422) from exc

    signal = audio_service.forensic_signal(path)
    quality = forensic_service.quality_report(path)
    waveform = audio_service.waveform_peaks(path, buckets=WAVEFORM_BUCKETS)

    details = analysis.model_details or {}
    sample_rate = analysis.sample_rate or info.sample_rate
    channels = analysis.channels or info.channels
    total_duration = (
        float(analysis.audio_duration) if analysis.audio_duration is not None else info.duration
    )
    analysed_seconds = float(signal["analysed_seconds"])

    audio = ForensicsAudioOut(
        duration_seconds=round(total_duration, 3),
        analysed_seconds=analysed_seconds,
        sample_rate_hz=sample_rate,
        channels=channels,
        frames=info.frames,
        container=(analysis.file_format or info.format or "").lower() or None,
        subtype=info.subtype,
        file_size_bytes=analysis.file_size_bytes or info.file_size_bytes,
        nyquist_hz=round(sample_rate / 2.0, 1) if sample_rate else None,
        channel_layout={1: "mono", 2: "stereo"}.get(channels, f"{channels} channels"),
        bit_depth=BIT_DEPTHS.get((info.subtype or "").upper()),
        average_bitrate_kbps=(
            round((analysis.file_size_bytes or info.file_size_bytes) * 8.0 / total_duration / 1000.0, 1)
            if total_duration
            else None
        ),
        truncated_for_analysis=bool(total_duration - analysed_seconds > 0.05),
    )

    model = ForensicsModelOut(
        status=analysis.analysis_status,
        predicted_class=analysis.predicted_class,
        model_score=analysis.model_score,
        model_version=analysis.model_version,
        threshold=details.get("threshold"),
        windows_analyzed=details.get("windows_analyzed"),
        window_seconds=details.get("window_seconds"),
        window_scores=[float(score) for score in (details.get("window_scores") or [])],
        aggregation=details.get("aggregation"),
        inference_ms=details.get("inference_ms") or analysis.analysis_duration_ms,
        parameters=details.get("parameters"),
        device=details.get("device"),
        failure_reason=analysis.failure_reason,
    )

    return ForensicsOut(
        analysis_id=analysis.id,
        filename=analysis.filename,
        source=analysis.source,
        file_format=analysis.file_format,
        created_at=analysis.created_at,
        audio=audio,
        waveform=ForensicsWaveformOut(
            peaks=waveform["peaks"],
            buckets=len(waveform["peaks"]),
            duration=waveform["duration"],
        ),
        signal=ForensicsSignalOut(
            rms_timeline=signal["rms_timeline"],
            band_energy=signal["band_energy"],
            spectral_centroid_hz=signal["spectral_centroid_hz"],
            spectral_rolloff_hz=signal["spectral_rolloff_hz"],
            zero_crossing_rate=signal["zero_crossing_rate"],
            peak_amplitude=signal["peak_amplitude"],
            silence_ratio=signal["silence_ratio"],
            note=signal["note"],
        ),
        quality=quality,
        model=model,
        evidence_note=EVIDENCE_NOTE,
        disclaimer=DISCLAIMER,
    )


@router.get(
    "/{analysis_id}/media",
    summary="Stream the stored recording for playback",
    response_class=FileResponse,
)
def get_forensics_media(
    analysis_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    analysis = get_owned_analysis(db, current_user, analysis_id)
    path = _resolve_audio(analysis)
    media_type = MEDIA_TYPES.get((analysis.file_format or "").lower(), "application/octet-stream")
    return FileResponse(
        path,
        media_type=media_type,
        filename=analysis.filename,
        content_disposition_type="inline",
        headers={"Cache-Control": "private, no-store"},
    )


@router.get(
    "/{analysis_id}/segment-signal",
    response_model=SegmentSignalOut,
    summary="Per-window signal measurements (independent of the model)",
)
def get_segment_signal(
    analysis_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SegmentSignalOut:
    """Measure each window's level/clipping/silence, using stored or default spans."""
    enforce(request, "analysis", f"user:{current_user.id}")
    analysis = get_owned_analysis(db, current_user, analysis_id)
    path = _resolve_audio(analysis)
    rows = segment_service.stored_segments(db, analysis.id)
    meta = analysis.segment_meta or {}

    if rows:
        spans = rows
    else:
        try:
            duration = float(
                analysis.audio_duration
                if analysis.audio_duration is not None
                else audio_service.probe_audio(path).duration
            )
            spans = segment_service.plan_segments(
                duration,
                float(meta.get("window_seconds") or settings.segment_window_seconds),
                float(meta.get("hop_seconds") or settings.segment_hop_seconds),
            )
        except audio_service.AudioProcessingError as exc:
            raise AppError(str(exc.message), code="audio_unreadable", status_code=422) from exc

    try:
        bundle = forensic_service.analysis_bundle(path, spans)
    except audio_service.AudioProcessingError as exc:
        raise AppError(str(exc.message), code="audio_unreadable", status_code=422) from exc

    return SegmentSignalOut(
        analysis_id=analysis.id,
        computed=bool(rows),
        total_segments=len(bundle["segments"]),
        quality=bundle["quality"],
        segments=bundle["segments"],
        note=bundle["note"],
    )


def _segments_payload(analysis, rows, meta, *, cached: bool = False) -> SegmentsOut:
    """Project stored segment rows + meta into the API response."""
    meta = meta or {}
    aggregate = meta.get("aggregate")
    return SegmentsOut(
        analysis_id=analysis.id,
        computed=bool(rows),
        cached=cached,
        computed_at=meta.get("computed_at"),
        window_seconds=meta.get("window_seconds"),
        hop_seconds=meta.get("hop_seconds"),
        overlap_ratio=meta.get("overlap_ratio"),
        sample_rate=meta.get("sample_rate"),
        total_duration=meta.get("total_duration"),
        total_segments=len(rows),
        model_id=meta.get("model_id"),
        model_version=meta.get("model_version"),
        segments=[
            SegmentOut(
                index=row.segment_index,
                start_seconds=row.start_seconds,
                end_seconds=row.end_seconds,
                duration_seconds=round(row.end_seconds - row.start_seconds, 4),
                state=row.state,
                label=row.label,
                score=row.score,
                reason=row.reason,
                model_version=row.model_version,
            )
            for row in rows
        ],
        aggregate=SegmentAggregateOut(**aggregate) if aggregate else None,
        caveat=meta.get("caveat") or segment_service.CAVEAT,
    )


@router.get(
    "/{analysis_id}/segments",
    response_model=SegmentsOut,
    summary="Stored segment-wise detection result",
)
def get_segments(
    analysis_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SegmentsOut:
    analysis = get_owned_analysis(db, current_user, analysis_id)
    rows = segment_service.stored_segments(db, analysis.id)
    if not rows:
        return _segments_payload(analysis, [], {}, cached=False)
    return _segments_payload(analysis, rows, analysis.segment_meta or {})


@router.post(
    "/{analysis_id}/segments",
    response_model=SegmentsOut,
    summary="Score the recording window by window (idempotent)",
)
def compute_segments(
    analysis_id: int,
    request: Request,
    window_seconds: float | None = Query(
        None, gt=0, le=30, description="Window length; defaults to the configured value."
    ),
    hop_seconds: float | None = Query(
        None, gt=0, le=30, description="Hop between windows; defaults to the configured value."
    ),
    force: bool = Query(False, description="Recompute and replace stored segments."),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SegmentsOut:
    enforce(request, "analysis", f"user:{current_user.id}")
    analysis = get_owned_analysis(db, current_user, analysis_id)
    path = _resolve_audio(analysis)

    if window_seconds is not None and hop_seconds is not None and hop_seconds > window_seconds:
        raise ValidationAppError("hop_seconds must not be larger than window_seconds.")

    try:
        rows, meta, cached = segment_service.compute_and_store(
            db,
            analysis,
            path=path,
            window=window_seconds,
            hop=hop_seconds,
            force=force,
        )
    except audio_service.AudioProcessingError as exc:
        raise AppError(str(exc.message), code="audio_unreadable", status_code=422) from exc

    return _segments_payload(analysis, rows, meta, cached=cached)
