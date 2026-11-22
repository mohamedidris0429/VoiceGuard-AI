"""Pydantic schemas for analytics and system status."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TrendPoint(BaseModel):
    date: str
    total: int
    genuine: int
    synthetic: int
    other: int


class BucketCount(BaseModel):
    label: str
    count: int


class SummaryOut(BaseModel):
    total_analyses: int
    genuine: int
    synthetic: int
    unavailable: int
    pending: int
    failed: int
    average_confidence: float | None = None
    average_duration: float | None = None
    total_audio_seconds: float | None = None
    last_analysis_at: datetime | None = None
    last_successful_at: datetime | None = None
    first_analysis_at: datetime | None = None


class TrendsOut(BaseModel):
    range_days: int
    daily: list[TrendPoint]
    confidence_buckets: list[BucketCount]
    duration_buckets: list[BucketCount]
    status_breakdown: list[BucketCount]


class ModelStatusOut(BaseModel):
    available: bool
    loaded: bool
    model_id: str
    model_version: str
    device: str
    sample_rate: int
    labels: dict[str, str]
    window_seconds: float
    max_windows: int
    threshold: float
    parameters: int | None = None
    detail: str | None = None


class HealthOut(BaseModel):
    status: str
    app: str
    version: str
    environment: str
    database: str
    model_available: bool
    uptime_seconds: int
    timestamp: datetime
    last_successful_analysis_at: datetime | None = None
