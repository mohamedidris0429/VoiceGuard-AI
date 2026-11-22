"""Segment-wise (windowed) detection of a stored recording - Phase 2.

The recording is split into overlapping segments. Every supported segment is
scored independently by the same pretrained detector used for the whole-file
analysis (``app.ai.detector.get_detector().predict``). No score is invented: a
segment that cannot be scored is stored with an explicit ``unsupported`` /
``error`` state and a ``NULL`` score, and is never reported as genuine/cloned.

Aggregation is a duration-weighted mean over the *completed* segments, reported
with the covered fraction of the file. Segment scores are probabilistic model
outputs, not proof of authenticity.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ai.detector import get_detector
from app.core.config import settings
from app.core.errors import AppError, ModelUnavailableError, ValidationAppError
from app.models.analysis import (
    PREDICTION_GENUINE,
    PREDICTION_SYNTHETIC,
    SEGMENT_DONE,
    SEGMENT_ERROR,
    SEGMENT_UNSUPPORTED,
    AnalysisSegment,
    AudioAnalysis,
)
from app.services import storage_service

logger = logging.getLogger("voiceguard.segments")

MIN_WINDOW_SECONDS = 0.5
MAX_WINDOW_SECONDS = 30.0
MIN_HOP_SECONDS = 0.1
DEFAULT_MIN_SEGMENT_SECONDS = 1.0
MAX_SEGMENTS = 60
SILENT_PEAK = 1e-4
RELIABLE_COVERAGE_RATIO = 0.95

AGGREGATION_METHOD = "duration-weighted mean over completed segments"

CAVEAT = (
    "Segment scores are probabilistic model outputs for individual windows, not proof of "
    "authenticity. A low score in one segment does not prove that audio is genuine, and a "
    "high score does not prove it is cloned. The aggregate covers only the completed "
    "segments - compare it with coverage_ratio before treating it as a whole-file result. "
    "When coverage is insufficient or segments were excluded, the whole-file label is "
    "null and the result is scoped as partial."
)


@dataclass(frozen=True)
class SegmentPlan:
    """One planned window. ``unsupported`` plans are never sent to the detector."""

    index: int
    start_seconds: float
    end_seconds: float
    state: str = SEGMENT_DONE
    reason: str | None = None

    @property
    def duration_seconds(self) -> float:
        return round(self.end_seconds - self.start_seconds, 6)


def clamp_plan(window: float, hop: float) -> tuple[float, float]:
    """Clamp window/hop to safe bounds; the hop never exceeds the window."""
    safe_window = min(max(float(window), MIN_WINDOW_SECONDS), MAX_WINDOW_SECONDS)
    safe_hop = min(max(float(hop), MIN_HOP_SECONDS), safe_window)
    return round(safe_window, 4), round(safe_hop, 4)


def plan_segments(
    duration_s: float,
    window: float = 4.0,
    hop: float = 2.0,
    min_duration: float = DEFAULT_MIN_SEGMENT_SECONDS,
) -> list[SegmentPlan]:
    """Plan overlapping segments covering the whole recording.

    The final segment is clamped to the real audio duration. A segment shorter
    than ``min_duration`` (typically the clamped tail) is returned with the
    ``unsupported`` state so the caller never invents a prediction for it.
    """
    duration = float(duration_s)
    if not math.isfinite(duration) or duration <= 0:
        raise ValidationAppError("The recording has no measurable duration.")

    safe_window, safe_hop = clamp_plan(window, hop)
    minimum = max(float(min_duration), 0.0)

    plans: list[SegmentPlan] = []
    start = 0.0
    while start < duration - 1e-9:
        end = round(min(start + safe_window, duration), 4)
        length = end - start
        if length < minimum:
            plans.append(
                SegmentPlan(
                    index=len(plans),
                    start_seconds=round(start, 4),
                    end_seconds=end,
                    state=SEGMENT_UNSUPPORTED,
                    reason=f"Segment is shorter than the {minimum:.2f}s minimum duration.",
                )
            )
        else:
            plans.append(
                SegmentPlan(
                    index=len(plans),
                    start_seconds=round(start, 4),
                    end_seconds=end,
                )
            )
        if end >= duration - 1e-9:
            break
        start = round(start + safe_hop, 4)

        if len(plans) >= MAX_SEGMENTS:
            raise ValidationAppError(
                f"This plan needs more than the {MAX_SEGMENTS} supported segments. "
                "Use a larger hop_seconds."
            )

    return plans


def _decode(path: Path, sample_rate: int) -> np.ndarray:
    """Decode the whole file to mono float32 at the model sample rate."""
    import librosa

    try:
        waveform, _ = librosa.load(str(path), sr=sample_rate, mono=True, dtype="float32")
    except Exception as exc:
        raise ValidationAppError(
            "The audio could not be decoded for segment analysis.",
            code="audio_processing_failed",
        ) from exc

    if waveform.size == 0:
        raise ValidationAppError(
            "The audio file contains no samples.", code="audio_processing_failed"
        )
    if not np.isfinite(waveform).all():
        raise ValidationAppError(
            "The audio contains invalid samples.", code="audio_processing_failed"
        )

    duration = float(waveform.size / sample_rate)
    if duration < settings.min_audio_seconds or duration > settings.max_audio_seconds:
        raise ValidationAppError(
            "The recording is outside the supported duration limits "
            f"({settings.min_audio_seconds:.0f}-{settings.max_audio_seconds:.0f}s)."
        )
    return waveform


def _union_seconds(intervals: list[tuple[float, float]]) -> float:
    """Total length covered by a set of (possibly overlapping) intervals."""
    if not intervals:
        return 0.0
    ordered = sorted(intervals)
    total = 0.0
    current_start, current_end = ordered[0]
    for start, end in ordered[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
        else:
            total += current_end - current_start
            current_start, current_end = start, end
    total += current_end - current_start
    return round(total, 6)


def aggregate_segments(
    rows: list[AnalysisSegment],
    total_duration: float,
    threshold: float,
    *,
    whole_file_score: float | None = None,
) -> dict:
    """Duration-weighted aggregation over completed segments, with coverage."""
    done = [row for row in rows if row.state == SEGMENT_DONE and row.score is not None]
    weighted = [(row.end_seconds - row.start_seconds, float(row.score)) for row in done]
    weight = sum(length for length, _ in weighted)
    score = sum(length * value for length, value in weighted) / weight if weight > 0 else None

    covered = _union_seconds([(row.start_seconds, row.end_seconds) for row in done])
    total = max(float(total_duration), 1e-6)
    coverage_ratio = round(min(1.0, covered / total), 4)

    unsupported = sum(1 for row in rows if row.state == SEGMENT_UNSUPPORTED)
    errors = sum(1 for row in rows if row.state == SEGMENT_ERROR)

    whole_file_reliable = bool(
        coverage_ratio >= RELIABLE_COVERAGE_RATIO
        and unsupported == 0
        and errors == 0
        and score is not None
    )

    # ``scored_label`` is the diagnostic label of the segments that were scored.
    # ``label`` is the whole-file verdict and only exists for reliable coverage, so
    # a partial result can never be rendered as a whole-file conclusion by a client
    # that reads ``label``.
    scored_label = None
    if score is not None:
        scored_label = PREDICTION_SYNTHETIC if score >= threshold else PREDICTION_GENUINE

    return {
        "method": AGGREGATION_METHOD,
        "score": round(score, 6) if score is not None else None,
        "label": scored_label if whole_file_reliable else None,
        "scored_label": scored_label,
        "scope": "whole_file" if whole_file_reliable else "partial",
        "threshold": round(float(threshold), 4),
        "completed_segments": len(done),
        "unsupported_segments": unsupported,
        "error_segments": errors,
        "excluded_segments": unsupported + errors,
        "coverage_seconds": round(covered, 3),
        "coverage_ratio": coverage_ratio,
        "whole_file_reliable": whole_file_reliable,
        "reliability_note": None
        if whole_file_reliable
        else _reliability_note(coverage_ratio, unsupported, errors, score),
        "whole_file_score": whole_file_score,
    }


def _reliability_note(
    coverage_ratio: float,
    unsupported: int,
    errors: int,
    score: float | None,
) -> str:
    """Explain why an aggregate is scoped as partial instead of whole-file."""
    if score is None:
        return (
            "No segment produced a score, so there is no aggregate verdict. "
            "See the per-segment states for details."
        )

    reasons: list[str] = []
    if coverage_ratio < RELIABLE_COVERAGE_RATIO:
        reasons.append(
            f"Coverage {coverage_ratio * 100:.1f}% is below the "
            f"{RELIABLE_COVERAGE_RATIO * 100:.0f}% threshold"
        )
    if unsupported or errors:
        reasons.append(
            f"{unsupported + errors} segment(s) were excluded "
            f"({unsupported} unsupported, {errors} error)"
        )
    return (
        "; ".join(reasons)
        + ". The score and scored_label describe the scored segments only, not the whole file."
    )


def stored_segments(db: Session, analysis_id: int) -> list[AnalysisSegment]:
    return list(
        db.scalars(
            select(AnalysisSegment)
            .where(AnalysisSegment.analysis_id == analysis_id)
            .order_by(AnalysisSegment.segment_index)
        ).all()
    )


def compute_and_store(
    db: Session,
    analysis: AudioAnalysis,
    *,
    path: Path | None = None,
    window: float | None = None,
    hop: float | None = None,
    force: bool = False,
) -> tuple[list[AnalysisSegment], dict, bool]:
    """Score every supported segment and persist the rows.

    Returns ``(rows, meta, cached)``. A second call without ``force`` returns the
    stored rows untouched (idempotent). Rows and ``analysis.segment_meta`` are
    written in a single transaction; when the model is unavailable nothing is
    stored and the error surfaces to the caller.
    """
    existing = stored_segments(db, analysis.id)
    if existing and not force:
        return existing, dict(analysis.segment_meta or {}), True

    path = path or storage_service.audio_path_for(analysis.stored_file_reference)
    if not path.exists():
        raise AppError(
            "The stored audio file is no longer available.",
            code="file_missing",
            status_code=410,
        )

    sample_rate = int(settings.model_sample_rate)
    waveform = _decode(path, sample_rate)
    total_duration = round(float(waveform.size / sample_rate), 4)

    safe_window, safe_hop = clamp_plan(
        settings.segment_window_seconds if window is None else window,
        settings.segment_hop_seconds if hop is None else hop,
    )
    plans = plan_segments(total_duration, safe_window, safe_hop)

    detector = get_detector()
    threshold = float(settings.synthetic_threshold)
    model_version: str | None = None
    rows: list[AnalysisSegment] = []

    for plan in plans:
        state = plan.state
        label: str | None = None
        score: float | None = None
        reason = plan.reason

        if state == SEGMENT_UNSUPPORTED:
            # Planned as unsupported (below the minimum duration): never scored.
            rows.append(
                AnalysisSegment(
                    analysis_id=analysis.id,
                    segment_index=plan.index,
                    start_seconds=plan.start_seconds,
                    end_seconds=plan.end_seconds,
                    state=state,
                    reason=reason,
                    model_name=settings.model_id,
                )
            )
            continue

        start_sample = int(round(plan.start_seconds * sample_rate))
        end_sample = min(int(round(plan.end_seconds * sample_rate)), waveform.size)
        chunk = waveform[start_sample:end_sample]

        if chunk.size == 0:
            state = SEGMENT_UNSUPPORTED
            reason = "Segment contains no samples."
        elif float(np.max(np.abs(chunk))) < SILENT_PEAK:
            state = SEGMENT_UNSUPPORTED
            reason = "Segment is silent; there is no speech to score."
        else:
            try:
                prediction = detector.predict(chunk, sample_rate)
            except ModelUnavailableError as exc:
                # Nothing is persisted: the caller reports the model as unavailable.
                raise AppError(exc.message, code="model_unavailable", status_code=409) from exc
            except AppError as exc:
                state = SEGMENT_ERROR
                reason = exc.message
            except Exception:  # unexpected inference failure for this segment only
                logger.exception(
                    "Segment %s of analysis %s failed", plan.index, analysis.id
                )
                state = SEGMENT_ERROR
                reason = "This segment could not be scored."
            else:
                score = round(float(prediction.synthetic_probability), 6)
                label = prediction.predicted_class
                model_version = prediction.model_version or model_version

        rows.append(
            AnalysisSegment(
                analysis_id=analysis.id,
                segment_index=plan.index,
                start_seconds=plan.start_seconds,
                end_seconds=plan.end_seconds,
                state=state,
                label=label,
                score=score,
                reason=reason,
                model_name=settings.model_id,
                model_version=model_version
                or getattr(detector, "_model_version", None)
                or analysis.model_version,
            )
        )

    aggregate = aggregate_segments(
        rows, total_duration, threshold, whole_file_score=analysis.model_score
    )
    computed_at = datetime.now(timezone.utc)
    meta = {
        "schema_version": 1,
        "window_seconds": safe_window,
        "hop_seconds": safe_hop,
        # A single-segment plan has no realised overlap, whatever the hop was.
        "overlap_ratio": round(max(0.0, 1.0 - (safe_hop / safe_window)), 4)
        if len(plans) > 1
        else 0.0,
        "sample_rate": sample_rate,
        "total_duration": total_duration,
        "total_segments": len(rows),
        "model_id": settings.model_id,
        "model_version": next((row.model_version for row in rows if row.model_version), None),
        "aggregate": aggregate,
        "caveat": CAVEAT,
        "computed_at": computed_at.isoformat(),
    }

    db.execute(delete(AnalysisSegment).where(AnalysisSegment.analysis_id == analysis.id))
    db.add_all(rows)
    analysis.segment_meta = meta
    db.add(analysis)
    db.commit()

    return stored_segments(db, analysis.id), meta, False

