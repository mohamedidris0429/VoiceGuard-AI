"""Pydantic schemas for segment-level analysis - Phase 2.

A segment row is the stored model output for one window of the recording. None
of these fields is proof about the audio inside that window: the score is a
probabilistic model output produced by the same pretrained detector used for the
whole-file analysis.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class SegmentOut(BaseModel):
    """One analysed segment of the recording."""

    index: int
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    state: str
    label: str | None = None
    score: float | None = None
    reason: str | None = None
    model_version: str | None = None


class SegmentAggregateOut(BaseModel):
    """Duration-weighted view over the segments that produced a score.

    ``label`` is a whole-file verdict and is only present when
    ``whole_file_reliable`` is true. Partial results keep their diagnostic
    ``score``/``scored_label`` but are marked ``scope="partial"``.
    """

    method: str
    score: float | None = None
    label: str | None = None
    scored_label: str | None = None
    scope: str = "partial"
    reliability_note: str | None = None
    threshold: float
    completed_segments: int
    unsupported_segments: int
    error_segments: int
    excluded_segments: int
    coverage_seconds: float
    coverage_ratio: float
    whole_file_reliable: bool
    whole_file_score: float | None = None

    @model_validator(mode="after")
    def _enforce_scope_contract(self) -> "SegmentAggregateOut":
        """A whole-file label may only exist when the aggregate is reliable.

        Enforced on the response model as well, so a stored aggregate written by
        an older build can never surface a partial result as a whole-file verdict.
        """
        if self.scored_label is None:
            self.scored_label = self.label
        if self.whole_file_reliable:
            self.scope = "whole_file"
        else:
            self.scope = "partial"
            self.label = None
        return self


class SegmentsOut(BaseModel):
    analysis_id: int
    computed: bool
    cached: bool = False
    computed_at: datetime | None = None
    window_seconds: float | None = None
    hop_seconds: float | None = None
    overlap_ratio: float | None = None
    sample_rate: int | None = None
    total_duration: float | None = None
    total_segments: int = 0
    model_id: str | None = None
    model_version: str | None = None
    segments: list[SegmentOut] = Field(default_factory=list)
    aggregate: SegmentAggregateOut | None = None
    caveat: str
