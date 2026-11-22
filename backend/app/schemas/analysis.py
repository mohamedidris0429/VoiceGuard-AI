"""Pydantic schemas for audio analysis endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AnalysisOut(BaseModel):
    """Public representation of an analysis (never exposes storage paths)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    source: str
    audio_duration: float | None = None
    sample_rate: int | None = None
    channels: int | None = None
    file_format: str | None = None
    file_size_bytes: int | None = None
    predicted_class: str | None = None
    model_score: float | None = None
    model_version: str | None = None
    analysis_status: str
    failure_reason: str | None = None
    analysis_duration_ms: int | None = None
    audio_features: dict | None = None
    model_details: dict | None = None
    created_at: datetime


class AnalyzeRequest(BaseModel):
    analysis_id: int = Field(gt=0)


class WaveformOut(BaseModel):
    peaks: list[float]
    duration: float
    sample_rate: int


class ComparisonOut(BaseModel):
    left: AnalysisOut
    right: AnalysisOut
    duration_delta_seconds: float | None = None
    score_delta: float | None = None
    disclaimer: str


class HistoryPage(BaseModel):
    items: list[AnalysisOut]
    total: int
    page: int
    page_size: int
    pages: int


class DeleteResult(BaseModel):
    message: str
    id: int
