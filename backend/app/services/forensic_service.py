"""Phase 3 - signal-quality measurements and per-segment forensic summaries.

Everything in this module is descriptive digital signal processing: peak and RMS
levels, clipping, DC offset, an SNR estimate, effective bandwidth, silence
structure and spectral flatness. None of it is evidence that a recording is
cloned or genuine, and none of it changes or overrides the model score.

Measurements are computed from the decoded audio (mono, 16 kHz, at most
``MAX_SECONDS``) so memory use stays bounded on low-RAM machines.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Iterable, Protocol

import numpy as np

from app.services.audio_service import AudioProcessingError

SAMPLE_RATE = 16000
MAX_SECONDS = 30.0
FRAME = 2048
HOP = 512

QUALITY_NOTE = (
    "These are measurements of the decoded signal (levels, clipping, DC offset, "
    "an SNR estimate, bandwidth and silence structure). They describe recording "
    "quality only and are not evidence of authenticity or of voice cloning."
)

SEGMENT_NOTE = (
    "Per-window signal measurements are computed independently of the model. "
    "They help explain why a window may be unreliable (for example silence or "
    "clipping); they do not confirm or contradict the model score."
)


class _Span(Protocol):  # pragma: no cover - structural typing only
    segment_index: int
    start_seconds: float
    end_seconds: float
    state: str


def _db(value: float) -> float:
    """Amplitude ratio -> dBFS, floored so silence never yields -inf."""
    return round(20.0 * math.log10(max(float(value), 1e-9)), 2)


def _load(path: Path) -> tuple[np.ndarray, int]:
    import librosa

    try:
        waveform, sample_rate = librosa.load(
            str(path), sr=SAMPLE_RATE, mono=True, dtype="float32", duration=MAX_SECONDS
        )
    except Exception as exc:
        raise AudioProcessingError(
            "The audio could not be decoded for signal measurement."
        ) from exc

    if waveform.size == 0:
        raise AudioProcessingError("The audio file contains no samples.")
    if not np.isfinite(waveform).all():
        raise AudioProcessingError("The audio contains invalid samples.")
    return waveform, int(sample_rate)


def _frame_rms(waveform: np.ndarray) -> np.ndarray:
    import librosa

    if waveform.size < FRAME:
        padded = np.zeros(FRAME, dtype=np.float32)
        padded[: waveform.size] = waveform
        waveform = padded
    frames = librosa.util.frame(waveform, frame_length=FRAME, hop_length=HOP)
    return np.sqrt(np.mean(np.square(frames, dtype=np.float64), axis=0))


def _runs(mask: np.ndarray) -> list[int]:
    """Lengths of consecutive True runs."""
    lengths: list[int] = []
    current = 0
    for flag in mask:
        if flag:
            current += 1
        elif current:
            lengths.append(current)
            current = 0
    if current:
        lengths.append(current)
    return lengths


def measure_quality(waveform: np.ndarray, sample_rate: int) -> dict[str, Any]:
    """Measure signal quality and derive transparent observations."""
    waveform = np.asarray(waveform, dtype=np.float32).reshape(-1)
    if waveform.size == 0:
        raise AudioProcessingError("The audio file contains no samples.")
    if not np.isfinite(waveform).all():
        raise AudioProcessingError("The audio contains invalid samples.")

    import librosa

    absolute = np.abs(waveform)
    peak = float(absolute.max())
    rms = float(np.sqrt(np.mean(np.square(waveform, dtype=np.float64))))
    clipping_ratio = float(np.mean(absolute >= 0.999))
    dc_offset = float(np.mean(waveform, dtype=np.float64))

    frame_rms = _frame_rms(waveform)
    frame_db = 20.0 * np.log10(np.maximum(frame_rms, 1e-9))
    noise_floor_db = float(np.percentile(frame_db, 10))
    speech_level_db = float(np.percentile(frame_db, 90))
    snr_estimate_db = round(speech_level_db - noise_floor_db, 2)
    dynamic_range_db = round(float(np.percentile(frame_db, 95) - np.percentile(frame_db, 5)), 2)

    silence_threshold = max(1e-4, float(np.mean(frame_rms)) * 0.25)
    silent_frames = frame_rms < silence_threshold
    silence_ratio = float(np.mean(silent_frames))
    frame_seconds = HOP / float(sample_rate)
    runs = _runs(silent_frames)
    longest_silence = round(max(runs) * frame_seconds, 3) if runs else 0.0

    leading = 0
    for flag in silent_frames:
        if not flag:
            break
        leading += 1
    trailing = 0
    for flag in silent_frames[::-1]:
        if not flag:
            break
        trailing += 1

    # Effective bandwidth: frequency below which 99% of the mean magnitude
    # spectrum lies. Bounded, frame-based STFT (no full-file FFT).
    effective_bandwidth = None
    spectral_flatness = None
    if peak >= 1e-5:
        spectrum = np.abs(
            librosa.stft(waveform, n_fft=FRAME, hop_length=HOP, window="hann")
        ).mean(axis=1)
        total = float(spectrum.sum())
        if total > 0:
            cumulative = np.cumsum(spectrum)
            index = int(np.searchsorted(cumulative, 0.99 * total))
            index = min(index, spectrum.size - 1)
            frequencies = librosa.fft_frequencies(sr=sample_rate, n_fft=FRAME)
            effective_bandwidth = round(float(frequencies[index]), 1)
        flatness = librosa.feature.spectral_flatness(y=waveform, n_fft=FRAME, hop_length=HOP)
        spectral_flatness = round(float(np.mean(flatness)), 5)

    crest_factor_db = round(_db(peak) - _db(rms), 2)

    measurements = {
        "peak_dbfs": _db(peak),
        "rms_dbfs": _db(rms),
        "crest_factor_db": crest_factor_db,
        "dynamic_range_db": dynamic_range_db,
        "clipping_ratio": round(clipping_ratio, 6),
        "dc_offset": round(dc_offset, 6),
        "snr_estimate_db": snr_estimate_db,
        "effective_bandwidth_hz": effective_bandwidth,
        "spectral_flatness": spectral_flatness,
        "silence_ratio": round(silence_ratio, 4),
        "leading_silence_seconds": round(leading * frame_seconds, 3),
        "trailing_silence_seconds": round(trailing * frame_seconds, 3),
        "longest_silence_seconds": longest_silence,
        "analysed_seconds": round(waveform.size / float(sample_rate), 2),
        "nyquist_hz": round(sample_rate / 2.0, 1),
        "observations": _observations(
            peak=peak,
            clipping_ratio=clipping_ratio,
            dc_offset=dc_offset,
            snr_estimate_db=snr_estimate_db,
            silence_ratio=silence_ratio,
            crest_factor_db=crest_factor_db,
            effective_bandwidth_hz=effective_bandwidth,
            nyquist_hz=sample_rate / 2.0,
            longest_silence=longest_silence,
        ),
        "note": QUALITY_NOTE,
    }
    return measurements


def _observations(
    *,
    peak: float,
    clipping_ratio: float,
    dc_offset: float,
    snr_estimate_db: float,
    silence_ratio: float,
    crest_factor_db: float,
    effective_bandwidth_hz: float | None,
    nyquist_hz: float,
    longest_silence: float,
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []

    def add(code: str, severity: str, title: str, detail: str) -> None:
        items.append(
            {"code": code, "severity": severity, "title": title, "detail": detail}
        )

    if peak < 1e-4:
        add(
            "silent",
            "warning",
            "Digitally silent recording",
            "Peak level is at or below the noise floor of 16-bit audio, so there is "
            "almost no signal to measure. No authenticity conclusion can be drawn.",
        )
        return items

    if clipping_ratio >= 0.001:
        add(
            "clipping",
            "warning",
            "Clipping detected",
            f"{clipping_ratio * 100:.2f}% of samples sit at full scale. Clipping adds "
            "harmonics that were not in the original speech and can distort both the "
            "signal measurements and a model score.",
        )
    elif clipping_ratio >= 0.0001:
        add(
            "clipping",
            "caution",
            "Occasional clipping",
            f"{clipping_ratio * 100:.3f}% of samples are at full scale. Usually audible "
            "as brief clicks; worth checking the recording gain.",
        )

    if abs(dc_offset) >= 0.05:
        add(
            "dc_offset",
            "warning",
            "Large DC offset",
            f"Mean sample value is {dc_offset:.3f}. A DC offset wastes headroom and "
            "shifts the waveform away from zero; it is a capture/processing artefact, "
            "not a sign of synthetic speech.",
        )
    elif abs(dc_offset) >= 0.01:
        add(
            "dc_offset",
            "caution",
            "Mild DC offset",
            f"Mean sample value is {dc_offset:.3f}. This is usually harmless and often "
            "comes from the recording interface.",
        )

    if snr_estimate_db < 10.0:
        add(
            "low_snr",
            "warning",
            "Low estimated SNR",
            f"Speech level is only {snr_estimate_db:.1f} dB above the quietest frames. "
            "Background noise at this level can dominate the model's input.",
        )
    elif snr_estimate_db < 20.0:
        add(
            "low_snr",
            "caution",
            "Moderate background noise",
            f"Estimated SNR is {snr_estimate_db:.1f} dB (speech vs quietest frames). "
            "Cleaner audio usually gives a more stable result.",
        )

    if effective_bandwidth_hz is not None and effective_bandwidth_hz < 0.35 * nyquist_hz:
        add(
            "band_limited",
            "caution",
            "Band-limited audio",
            f"99% of the spectral energy is below {effective_bandwidth_hz:.0f} Hz, while "
            f"the stream supports up to {nyquist_hz:.0f} Hz. This is typical of "
            "telephone/compressed audio and of heavy low-pass processing.",
        )

    if silence_ratio >= 0.6:
        add(
            "mostly_silent",
            "caution",
            "Mostly silent",
            f"{silence_ratio * 100:.0f}% of frames are near-silent and the longest gap "
            f"is {longest_silence:.1f}s. Short or sparse speech lowers confidence.",
        )

    if crest_factor_db < 6.0:
        add(
            "compressed",
            "caution",
            "Heavily compressed dynamics",
            f"Crest factor is {crest_factor_db:.1f} dB. Strong compression or limiting "
            "reduces natural level variation.",
        )

    if not items:
        add(
            "clean",
            "info",
            "No strong quality problems measured",
            "No clipping, DC offset, unusual silence or bandwidth limitation was "
            "detected by these thresholds. This is a recording-quality observation "
            "only; it says nothing about whether the voice is cloned.",
        )
    return items


def quality_report(path: Path) -> dict[str, Any]:
    waveform, sample_rate = _load(path)
    return measure_quality(waveform, sample_rate)


def _segment_metrics(waveform: np.ndarray, sample_rate: int, start: float, end: float) -> dict:
    first = max(0, int(round(start * sample_rate)))
    last = min(waveform.size, int(round(end * sample_rate)))
    if last <= first:
        return {
            "rms_dbfs": None,
            "peak_dbfs": None,
            "silence_ratio": None,
            "clipping_ratio": None,
            "spectral_centroid_hz": None,
        }

    import librosa

    window = waveform[first:last]
    absolute = np.abs(window)
    peak = float(absolute.max())
    rms = float(np.sqrt(np.mean(np.square(window, dtype=np.float64))))
    frame_rms = _frame_rms(window)
    threshold = max(1e-4, float(np.mean(frame_rms)) * 0.25)
    centroid = librosa.feature.spectral_centroid(
        y=window, sr=sample_rate, n_fft=min(FRAME, max(512, window.size)), hop_length=HOP
    )
    return {
        "rms_dbfs": _db(rms),
        "peak_dbfs": _db(peak),
        "silence_ratio": round(float(np.mean(frame_rms < threshold)), 4),
        "clipping_ratio": round(float(np.mean(absolute >= 0.999)), 6),
        "spectral_centroid_hz": round(float(np.mean(centroid)), 1),
    }


def segment_signals(
    waveform: np.ndarray, sample_rate: int, spans: Iterable[Any]
) -> list[dict[str, Any]]:
    """Measure each planned/stored span on the same decoded audio."""
    results: list[dict[str, Any]] = []
    for span in spans:
        start = float(span.start_seconds)
        end = float(span.end_seconds)
        index = getattr(span, "segment_index", None)
        if index is None:
            index = getattr(span, "index", len(results))
        results.append(
            {
                "index": int(index),
                "start_seconds": round(start, 4),
                "end_seconds": round(end, 4),
                "duration_seconds": round(max(0.0, end - start), 4),
                "state": str(span.state),
                **_segment_metrics(waveform, sample_rate, start, end),
            }
        )
    return results


def analysis_bundle(path: Path, spans: Iterable[Any]) -> dict[str, Any]:
    """Single decode -> quality measurements plus per-segment signal metrics."""
    waveform, sample_rate = _load(path)
    if float(np.max(np.abs(waveform))) < 1e-4:
        raise AudioProcessingError(
            "The recording is silent, so no signal measurements can be computed."
        )
    return {
        "quality": measure_quality(waveform, sample_rate),
        "segments": segment_signals(waveform, sample_rate, spans),
        "sample_rate": sample_rate,
        "analysed_seconds": round(waveform.size / float(sample_rate), 2),
        "note": SEGMENT_NOTE,
    }
