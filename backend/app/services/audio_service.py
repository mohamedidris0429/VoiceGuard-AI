"""Audio inspection, validation, preprocessing and descriptive feature extraction.

Library: librosa (STFT / MFCC) and soundfile (container parsing). Everything is
CPU only and bounded in memory: files are limited by size and duration before
any full decode happens.

The handcrafted features produced here are *descriptive* (they describe the
signal). They are deliberately never used as evidence of synthetic speech.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from app.core.config import settings
from app.core.errors import ValidationAppError

MAX_FEATURE_SECONDS = 30.0


@dataclass
class AudioInfo:
    duration: float
    sample_rate: int
    channels: int
    format: str
    subtype: str | None
    frames: int
    file_size_bytes: int


class AudioProcessingError(ValidationAppError):
    code = "audio_processing_failed"


def probe_audio(path: Path, *, declared_format: str | None = None) -> AudioInfo:
    """Read container metadata without decoding the whole file."""
    if not path.exists():
        raise AudioProcessingError("The audio file could not be found.")
    try:
        with sf.SoundFile(str(path)) as handle:
            frames = len(handle)
            sample_rate = int(handle.samplerate)
            channels = int(handle.channels)
            fmt = (handle.format or "").upper()
            subtype = handle.subtype
    except Exception as exc:  # malformed container / codec problems
        raise AudioProcessingError(
            "The audio file could not be decoded. It may be corrupt or use an unsupported codec."
        ) from exc

    if frames <= 0 or sample_rate <= 0:
        raise AudioProcessingError("The audio file contains no decodable audio.")

    duration = frames / float(sample_rate)

    if declared_format and fmt and declared_format.upper() not in fmt:
        raise AudioProcessingError(
            f"Expected a {declared_format.upper()} file but the container is {fmt or 'unknown'}."
        )
    if sample_rate < settings.min_sample_rate:
        raise AudioProcessingError(
            f"Sample rate {sample_rate} Hz is too low. Minimum supported is {settings.min_sample_rate} Hz."
        )
    if sample_rate > settings.max_sample_rate:
        raise AudioProcessingError(f"Sample rate {sample_rate} Hz is not supported.")
    if channels < 1 or channels > 8:
        raise AudioProcessingError("Unsupported channel layout.")
    if duration < settings.min_audio_seconds:
        raise AudioProcessingError(
            f"Audio is too short ({duration:.2f}s). Minimum is {settings.min_audio_seconds:.1f}s."
        )
    if duration > settings.max_audio_seconds:
        raise AudioProcessingError(
            f"Audio is too long ({duration:.1f}s). Maximum is {settings.max_audio_seconds:.0f}s."
        )

    return AudioInfo(
        duration=round(duration, 3),
        sample_rate=sample_rate,
        channels=channels,
        format=fmt.lower() or (declared_format or "unknown"),
        subtype=subtype,
        frames=frames,
        file_size_bytes=path.stat().st_size,
    )


def load_model_input(path: Path, target_sample_rate: int | None = None) -> tuple[np.ndarray, int]:
    """Decode to mono float32 at the model sample rate, with light silence trim.

    Loading at the target rate keeps memory low: 60 s mono @16 kHz is ~3.8 MB.
    """
    import librosa

    target = int(target_sample_rate or settings.model_sample_rate)
    try:
        waveform, sr = librosa.load(str(path), sr=target, mono=True, dtype="float32")
    except Exception as exc:
        raise AudioProcessingError(
            "The audio could not be decoded for analysis."
        ) from exc

    if waveform.size == 0:
        raise AudioProcessingError("The audio file contains no samples.")
    if not np.isfinite(waveform).all():
        raise AudioProcessingError("The audio contains invalid samples.")

    peak = float(np.max(np.abs(waveform)))
    if peak < 1e-4:
        raise AudioProcessingError("The recording is silent. No speech could be analysed.")

    # Remove leading/trailing near-silence, keeping at least ~0.5 s of audio.
    try:
        trimmed, _ = librosa.effects.trim(waveform, top_db=40.0, frame_length=2048, hop_length=512)
        if trimmed.size >= int(0.5 * sr) and trimmed.size < waveform.size:
            waveform = trimmed
    except Exception:  # pragma: no cover - trim is a best-effort enhancement
        pass

    return waveform.astype(np.float32, copy=False), int(sr)


def waveform_peaks(path: Path, buckets: int = 800) -> dict:
    """Downsampled peak envelope for waveform rendering (cheap, low memory)."""
    import librosa

    preview_sr = 4000
    waveform, sr = librosa.load(str(path), sr=preview_sr, mono=True, dtype="float32")
    if waveform.size == 0:
        return {"peaks": [], "duration": 0.0, "sample_rate": sr}

    buckets = max(32, min(buckets, 2000))
    if waveform.size < buckets:
        padded = np.zeros(buckets, dtype=np.float32)
        padded[: waveform.size] = waveform
        waveform = padded

    # Pad to a whole number of buckets, then take the max absolute value per bucket.
    chunk = int(math.ceil(waveform.size / buckets))
    total = chunk * buckets
    padded = np.zeros(total, dtype=np.float32)
    padded[: waveform.size] = waveform
    frames = padded.reshape(buckets, chunk)
    peaks = np.abs(frames).max(axis=1)
    scale = float(peaks.max()) or 1.0
    return {
        "peaks": [round(float(value / scale), 4) for value in peaks],
        "duration": round(waveform.size / sr, 3),
        "sample_rate": sr,
    }


def spectrogram_png(path: Path, max_width: int = 720, max_height: int = 260) -> bytes:
    """Render a mel spectrogram heat-map as PNG using Pillow (no matplotlib)."""
    import librosa
    from PIL import Image

    waveform, sr = librosa.load(str(path), sr=16000, mono=True, dtype="float32")
    if waveform.size == 0:
        raise AudioProcessingError("The audio contains no samples.")

    n_fft = 1024
    hop = 512
    mel = librosa.feature.melspectrogram(
        y=waveform, sr=sr, n_fft=n_fft, hop_length=hop, n_mels=96, fmax=8000
    )
    mel_db = librosa.power_to_db(mel, ref=np.max)

    # Normalise to 0..1 over a 70 dB window and transpose to (time, frequency).
    clipped = np.clip((mel_db + 70.0) / 70.0, 0.0, 1.0)
    image_array = clipped.T  # rows = time frames, columns = mel bins

    frames, bins = image_array.shape
    width = int(min(max_width, max(64, frames)))
    height = int(min(max_height, max(64, bins)))

    # Nearest-neighbour downsample without scipy/pandas dependencies.
    row_idx = np.linspace(0, frames - 1, height).astype(np.int32)
    col_idx = np.linspace(0, bins - 1, width).astype(np.int32)
    sampled = image_array[np.ix_(row_idx, col_idx)]

    rgb = _apply_colormap(sampled)
    image = Image.fromarray(rgb, mode="RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _apply_colormap(values: np.ndarray) -> np.ndarray:
    """Dark navy -> teal -> neon green gradient, matching the VoiceGuard palette."""
    stops = np.array(
        [
            [8, 15, 28],      # #080F1C
            [19, 60, 82],
            [20, 184, 166],   # #14B8A6
            [34, 197, 94],    # #22C55E
            [226, 255, 236],
        ],
        dtype=np.float32,
    )
    positions = np.linspace(0.0, 1.0, len(stops))
    flat = values.reshape(-1)
    channels = [np.interp(flat, positions, stops[:, channel]) for channel in range(3)]
    rgb = np.stack(channels, axis=1).reshape(values.shape + (3,))
    return rgb.astype(np.uint8)


def extract_features(path: Path) -> dict:
    """Compute descriptive signal features (never used as a verdict)."""
    import librosa

    try:
        waveform, sr = librosa.load(
            str(path), sr=16000, mono=True, dtype="float32", duration=MAX_FEATURE_SECONDS
        )
    except Exception as exc:
        raise AudioProcessingError("Feature extraction failed for this file.") from exc

    if waveform.size < 2048:
        raise AudioProcessingError("Audio is too short for feature extraction.")

    n_fft = 2048
    hop = 512

    mfcc = librosa.feature.mfcc(y=waveform, sr=sr, n_mfcc=13, n_fft=n_fft, hop_length=hop)
    centroid = librosa.feature.spectral_centroid(y=waveform, sr=sr, n_fft=n_fft, hop_length=hop)
    rolloff = librosa.feature.spectral_rolloff(
        y=waveform, sr=sr, n_fft=n_fft, hop_length=hop, roll_percent=0.85
    )
    bandwidth = librosa.feature.spectral_bandwidth(y=waveform, sr=sr, n_fft=n_fft, hop_length=hop)
    zcr = librosa.feature.zero_crossing_rate(waveform, frame_length=n_fft, hop_length=hop)
    rms = librosa.feature.rms(y=waveform, frame_length=n_fft, hop_length=hop)

    rms_values = rms.reshape(-1)
    silence_threshold = max(1e-4, float(np.mean(rms_values)) * 0.25)
    silence_ratio = float(np.mean(rms_values < silence_threshold))

    def _r(value: float, digits: int = 3) -> float:
        return round(float(value), digits)

    return {
        "analysed_seconds": _r(waveform.size / sr, 2),
        "sample_rate": sr,
        "mfcc_mean": [_r(value, 2) for value in mfcc.mean(axis=1)],
        "mfcc_std": [_r(value, 2) for value in mfcc.std(axis=1)],
        "spectral_centroid_hz": _r(np.mean(centroid), 1),
        "spectral_rolloff_hz": _r(np.mean(rolloff), 1),
        "spectral_bandwidth_hz": _r(np.mean(bandwidth), 1),
        "zero_crossing_rate": _r(np.mean(zcr), 5),
        "rms_energy": _r(np.mean(rms_values), 5),
        "peak_amplitude": _r(float(np.max(np.abs(waveform))), 4),
        "silence_ratio": _r(silence_ratio, 3),
    }

# ---------------------------------------------------------------------------
# Phase 1 - audio forensics signal measurements
# ---------------------------------------------------------------------------

FORENSIC_MAX_SECONDS = 30.0
FORENSIC_RMS_POINTS = 160
FORENSIC_SIGNAL_NOTE = (
    "These charts are measurements of the uploaded signal. They describe what the "
    "file contains; they are not evidence of authenticity, identity or intent."
)
FORENSIC_BANDS: tuple[tuple[str, float, float], ...] = (
    ("0–250 Hz", 0.0, 250.0),
    ("250–500 Hz", 250.0, 500.0),
    ("500 Hz–1 kHz", 500.0, 1000.0),
    ("1–2 kHz", 1000.0, 2000.0),
    ("2–4 kHz", 2000.0, 4000.0),
    ("4–8 kHz", 4000.0, 8000.0),
)


def _band_energy_shares(waveform: np.ndarray, sample_rate: int) -> list[dict]:
    """Average power spectrum split into fixed bands, computed in bounded chunks."""
    import librosa

    n_fft = 2048
    hop = 1024
    block_hop = hop * 64
    indices = np.arange(n_fft, dtype=np.float32)
    window = (0.5 - 0.5 * np.cos(2.0 * np.pi * indices / (n_fft - 1))).astype(np.float32)
    power = np.zeros(n_fft // 2 + 1, dtype=np.float64)

    if waveform.size >= n_fft:
        start = 0
        while start + n_fft <= waveform.size:
            block = waveform[start : start + n_fft + block_hop]
            frames = librosa.util.frame(block, frame_length=n_fft, hop_length=hop).T
            spectrum = np.abs(np.fft.rfft(frames * window, axis=1)) ** 2
            power += spectrum.sum(axis=0)
            start += block_hop
    else:
        padded = np.zeros(n_fft, dtype=np.float32)
        padded[: waveform.size] = waveform
        power += np.abs(np.fft.rfft(padded * window)) ** 2

    frequencies = np.fft.rfftfreq(n_fft, d=1.0 / sample_rate)
    total = float(power.sum())
    nyquist = sample_rate / 2.0

    bands: list[dict] = []
    for label, low, high in FORENSIC_BANDS:
        if low >= nyquist:
            continue
        upper = min(high, nyquist)
        if upper >= nyquist:
            mask = (frequencies >= low) & (frequencies <= upper)
        else:
            mask = (frequencies >= low) & (frequencies < upper)
        energy = float(power[mask].sum()) if mask.any() else 0.0
        bands.append(
            {
                "label": label,
                "low_hz": round(low, 1),
                "high_hz": round(upper, 1),
                "share": round(energy / total, 4) if total > 0 else 0.0,
            }
        )
    return bands


def forensic_signal(path: Path) -> dict:
    """Bounded, read-only measurements used by the forensics workspace."""
    import librosa

    try:
        waveform, sample_rate = librosa.load(
            str(path), sr=16000, mono=True, dtype="float32", duration=FORENSIC_MAX_SECONDS
        )
    except Exception as exc:
        raise AudioProcessingError(
            "The audio could not be decoded for forensic inspection."
        ) from exc

    if waveform.size < 2048:
        raise AudioProcessingError("The recording is too short for signal visualisation.")
    if not np.isfinite(waveform).all():
        raise AudioProcessingError("The audio contains invalid samples.")

    frame_length = 2048
    hop = 512
    rms = librosa.feature.rms(
        y=waveform, frame_length=frame_length, hop_length=hop
    ).reshape(-1)
    times = librosa.frames_to_time(np.arange(rms.size), sr=sample_rate, hop_length=hop)

    point_count = int(min(FORENSIC_RMS_POINTS, rms.size))
    picks = np.linspace(0, max(0, rms.size - 1), num=point_count).astype(np.int64)
    rms_peak = float(np.max(rms)) or 1e-9

    centroid = librosa.feature.spectral_centroid(
        y=waveform, sr=sample_rate, n_fft=frame_length, hop_length=hop
    )
    rolloff = librosa.feature.spectral_rolloff(
        y=waveform, sr=sample_rate, n_fft=frame_length, hop_length=hop, roll_percent=0.85
    )
    zcr = librosa.feature.zero_crossing_rate(
        waveform, frame_length=frame_length, hop_length=hop
    )
    silence_threshold = max(1e-4, float(np.mean(rms)) * 0.25)

    return {
        "analysed_seconds": round(float(waveform.size / sample_rate), 2),
        "sample_rate_hz": int(sample_rate),
        "rms_timeline": {
            "times": [round(float(times[i]), 3) for i in picks],
            "rms": [round(float(rms[i] / rms_peak), 4) for i in picks],
        },
        "band_energy": _band_energy_shares(waveform, sample_rate),
        "spectral_centroid_hz": round(float(np.mean(centroid)), 1),
        "spectral_rolloff_hz": round(float(np.mean(rolloff)), 1),
        "zero_crossing_rate": round(float(np.mean(zcr)), 5),
        "peak_amplitude": round(float(np.max(np.abs(waveform))), 4),
        "silence_ratio": round(float(np.mean(rms < silence_threshold)), 3),
        "note": FORENSIC_SIGNAL_NOTE,
    }

