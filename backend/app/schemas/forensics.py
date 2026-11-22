"""Pydantic schemas for the audio forensics workspace (Phase 1).

Everything here describes measurements of the stored audio file. None of these
fields is a claim that the recording is genuine or cloned.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ForensicsAudioOut(BaseModel):
    """Container and stream metadata for the inspected recording."""

    duration_seconds: float | None = None
    analysed_seconds: float
    sample_rate_hz: int | None = None
    channels: int | None = None
    frames: int | None = None
    container: str | None = None
    subtype: str | None = None
    file_size_bytes: int | None = None
    nyquist_hz: float | None = None
    channel_layout: str | None = None
    bit_depth: int | None = None
    average_bitrate_kbps: float | None = None
    truncated_for_analysis: bool = False


class ForensicsWaveformOut(BaseModel):
    """Downsampled peak envelope used for the interactive waveform."""

    peaks: list[float]
    buckets: int
    duration: float


class RmsTimelineOut(BaseModel):
    """Loudness envelope over time (normalised 0..1 plus timestamps)."""

    times: list[float]
    rms: list[float]


class BandEnergyOut(BaseModel):
    """Relative energy share of one fixed frequency band."""

    label: str
    low_hz: float
    high_hz: float
    share: float


class ForensicsSignalOut(BaseModel):
    """Measured signal characteristics (visualisation data, never evidence)."""

    rms_timeline: RmsTimelineOut
    band_energy: list[BandEnergyOut]
    spectral_centroid_hz: float | None = None
    spectral_rolloff_hz: float | None = None
    zero_crossing_rate: float | None = None
    peak_amplitude: float | None = None
    silence_ratio: float | None = None
    note: str


class QualityObservationOut(BaseModel):
    """One transparent interpretation of a measured signal condition."""

    code: str
    severity: str  # info | caution | warning
    title: str
    detail: str


class ForensicsQualityOut(BaseModel):
    """Recording-quality measurements (descriptive DSP only)."""

    peak_dbfs: float
    rms_dbfs: float
    crest_factor_db: float
    dynamic_range_db: float
    clipping_ratio: float
    dc_offset: float
    snr_estimate_db: float
    effective_bandwidth_hz: float | None = None
    spectral_flatness: float | None = None
    silence_ratio: float
    leading_silence_seconds: float
    trailing_silence_seconds: float
    longest_silence_seconds: float
    analysed_seconds: float
    nyquist_hz: float
    observations: list[QualityObservationOut] = Field(default_factory=list)
    note: str


class ForensicsSegmentSignalOut(BaseModel):
    """Signal measurements for one window (independent of the model)."""

    index: int
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    state: str
    rms_dbfs: float | None = None
    peak_dbfs: float | None = None
    silence_ratio: float | None = None
    clipping_ratio: float | None = None
    spectral_centroid_hz: float | None = None


class SegmentSignalOut(BaseModel):
    analysis_id: int
    computed: bool = False
    total_segments: int = 0
    quality: ForensicsQualityOut
    segments: list[ForensicsSegmentSignalOut] = Field(default_factory=list)
    note: str


class ForensicsModelOut(BaseModel):
    """Stored model output for this analysis (no new inference is run)."""

    status: str
    predicted_class: str | None = None
    model_score: float | None = None
    model_version: str | None = None
    threshold: float | None = None
    windows_analyzed: int | None = None
    window_seconds: float | None = None
    window_scores: list[float] = Field(default_factory=list)
    aggregation: str | None = None
    inference_ms: int | None = None
    parameters: int | None = None
    device: str | None = None
    failure_reason: str | None = None


class ForensicsOut(BaseModel):
    analysis_id: int
    filename: str
    source: str
    file_format: str | None = None
    created_at: datetime
    audio: ForensicsAudioOut
    waveform: ForensicsWaveformOut
    signal: ForensicsSignalOut
    quality: ForensicsQualityOut
    model: ForensicsModelOut
    evidence_note: str
    disclaimer: str
