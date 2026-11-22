"""Phase 4 - live (chunked near-real-time) analysis contracts."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class StreamChunkOut(BaseModel):
    index: int
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    score: float
    label: str
    peak: float
    latency_ms: int
    model_version: str | None = None


class StreamSessionOut(BaseModel):
    session_id: str
    status: str
    mode: str
    chunk_seconds: float
    created_at: datetime
    total_chunks: int
    scored_chunks: int
    duration_seconds: float
    average_score: float | None = None
    chunks: list[StreamChunkOut] = Field(default_factory=list)
    model_id: str
    model_version: str | None = None
    window_note: str
    latency_note: str
    caveat: str


class StreamSessionCreate(BaseModel):
    chunk_seconds: float = 3.0
