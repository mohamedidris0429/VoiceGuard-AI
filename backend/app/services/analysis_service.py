"""Analysis orchestration: validate -> preprocess -> infer -> persist."""

from __future__ import annotations

import logging
import time

from sqlalchemy.orm import Session

from app.ai.detector import get_detector
from app.core.config import settings
from app.core.errors import AppError, ModelUnavailableError
from app.models.analysis import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_UNAVAILABLE,
    AudioAnalysis,
)
from app.models.user import User
from app.services import audio_service
from app.services.storage_service import StoredFile, audio_path_for

logger = logging.getLogger("voiceguard.analysis")


def create_analysis(
    db: Session, user: User, stored: StoredFile, *, source: str = "upload"
) -> AudioAnalysis:
    """Validate the stored file and create a pending analysis row."""
    info = audio_service.probe_audio(stored.path, declared_format=stored.file_format)
    analysis = AudioAnalysis(
        user_id=user.id,
        filename=stored.filename,
        stored_file_reference=stored.reference,
        audio_duration=info.duration,
        sample_rate=info.sample_rate,
        channels=info.channels,
        file_format=stored.file_format,
        file_size_bytes=info.file_size_bytes,
        source=source,
        analysis_status=STATUS_PENDING,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


def run_analysis(db: Session, analysis: AudioAnalysis) -> AudioAnalysis:
    """Run real inference on the stored audio and persist the outcome."""
    path = audio_path_for(analysis.stored_file_reference)
    started = time.perf_counter()

    try:
        waveform, sample_rate = audio_service.load_model_input(
            path, settings.model_sample_rate
        )
        prediction = get_detector().predict(waveform, sample_rate)

        features = None
        try:
            features = audio_service.extract_features(path)
        except Exception as exc:  # features are descriptive only; never block a verdict
            logger.warning("Feature extraction failed for analysis %s: %s", analysis.id, exc)

        analysis.predicted_class = prediction.predicted_class
        analysis.model_score = round(prediction.synthetic_probability, 6)
        analysis.model_version = prediction.model_version
        analysis.analysis_status = STATUS_COMPLETED
        analysis.failure_reason = None
        analysis.model_details = prediction.as_dict()
        analysis.audio_features = features
    except ModelUnavailableError as exc:
        logger.warning("Model unavailable for analysis %s: %s", analysis.id, exc.message)
        analysis.analysis_status = STATUS_UNAVAILABLE
        analysis.failure_reason = exc.message
        analysis.predicted_class = None
        analysis.model_score = None
    except AppError as exc:
        logger.warning("Analysis %s failed validation: %s", analysis.id, exc.message)
        analysis.analysis_status = STATUS_FAILED
        analysis.failure_reason = exc.message
        analysis.predicted_class = None
        analysis.model_score = None
    except Exception:
        logger.exception("Unexpected failure while analysing %s", analysis.id)
        analysis.analysis_status = STATUS_FAILED
        analysis.failure_reason = "The analysis could not be completed. Please try again."
        analysis.predicted_class = None
        analysis.model_score = None
    finally:
        analysis.analysis_duration_ms = int((time.perf_counter() - started) * 1000)
        db.add(analysis)
        db.commit()
        db.refresh(analysis)

    return analysis


def analyze_stored_file(
    db: Session, user: User, stored: StoredFile, *, source: str = "upload"
) -> AudioAnalysis:
    analysis = create_analysis(db, user, stored, source=source)
    return run_analysis(db, analysis)
