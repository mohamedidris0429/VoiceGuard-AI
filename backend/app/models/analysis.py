"""Audio analysis and report models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, utcnow

if TYPE_CHECKING:  # pragma: no cover
    from app.models.user import User


# Analysis lifecycle
STATUS_PENDING = "pending"
STATUS_COMPLETED = "completed"
STATUS_UNAVAILABLE = "unavailable"
STATUS_FAILED = "failed"

PREDICTION_GENUINE = "genuine"
PREDICTION_SYNTHETIC = "synthetic"

# Segment-wise detection lifecycle (Phase 2)
SEGMENT_DONE = "done"
SEGMENT_UNSUPPORTED = "unsupported"
SEGMENT_ERROR = "error"


class AudioAnalysis(Base):
    __tablename__ = "audio_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_file_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    audio_duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_format: Mapped[str | None] = mapped_column(String(16), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="upload", nullable=False)

    predicted_class: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    analysis_status: Mapped[str] = mapped_column(
        String(24), default=STATUS_PENDING, nullable=False
    )
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    analysis_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    audio_features: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    model_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Phase 2: window/hop/model/aggregate description for the stored segments.
    segment_meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="analyses")
    reports: Mapped[list["Report"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan", passive_deletes=True
    )
    segments: Mapped[list["AnalysisSegment"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        Index("ix_audio_analyses_user_created", "user_id", "created_at"),
        Index("ix_audio_analyses_user_status", "user_id", "analysis_status"),
        Index("ix_audio_analyses_user_class", "user_id", "predicted_class"),
    )


class AnalysisSegment(Base):
    """One window of a recording, analysed individually (Phase 2).

    Rows are only written by the segment service after the real detector ran on
    that window (``done``) or after the window was deliberately not scored
    (``unsupported`` / ``error``). No placeholder score is ever stored.
    """

    __tablename__ = "analysis_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("audio_analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    state: Mapped[str] = mapped_column(String(16), default=SEGMENT_DONE, nullable=False)
    label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    analysis: Mapped["AudioAnalysis"] = relationship(back_populates="segments")

    __table_args__ = (
        UniqueConstraint(
            "analysis_id", "segment_index", name="uq_analysis_segments_analysis_index"
        ),
        Index("ix_analysis_segments_analysis_order", "analysis_id", "segment_index"),
    )


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("audio_analyses.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    report_reference: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    analysis: Mapped["AudioAnalysis"] = relationship(back_populates="reports")
