"""Audio processing unit tests (probing, features, waveform, spectrogram)."""

from __future__ import annotations

import numpy as np
import pytest

from app.core.errors import ValidationAppError
from app.services import audio_service


def test_probe_reads_real_metadata(wav_file):
    info = audio_service.probe_audio(wav_file, declared_format="wav")
    assert info.sample_rate == 16000
    assert info.channels == 1
    assert info.format.startswith("wav")
    assert 2.9 <= info.duration <= 3.1
    assert info.file_size_bytes > 0


def test_probe_rejects_too_short(short_wav_file):
    with pytest.raises(ValidationAppError, match="too short"):
        audio_service.probe_audio(short_wav_file)


def test_probe_rejects_missing_file(audio_dir):
    with pytest.raises(ValidationAppError):
        audio_service.probe_audio(audio_dir / "does-not-exist.wav")


def test_probe_rejects_format_mismatch(wav_file):
    with pytest.raises(ValidationAppError, match="Expected"):
        audio_service.probe_audio(wav_file, declared_format="mp3")


def test_load_model_input_resamples_to_16k(wav_file):
    waveform, sample_rate = audio_service.load_model_input(wav_file, 16000)
    assert sample_rate == 16000
    assert waveform.dtype == np.float32
    assert waveform.ndim == 1
    seconds = waveform.size / sample_rate
    assert 0.5 <= seconds <= 3.1
    assert np.max(np.abs(waveform)) > 0.01


def test_features_are_descriptive_numbers(wav_file):
    features = audio_service.extract_features(wav_file)
    assert len(features["mfcc_mean"]) == 13
    assert len(features["mfcc_std"]) == 13
    assert features["spectral_centroid_hz"] > 0
    assert features["spectral_rolloff_hz"] >= features["spectral_centroid_hz"] * 0.5
    assert 0.0 <= features["zero_crossing_rate"] <= 1.0
    assert features["rms_energy"] > 0
    assert 0.0 <= features["silence_ratio"] <= 1.0


def test_waveform_peaks_are_normalised(wav_file):
    data = audio_service.waveform_peaks(wav_file, buckets=200)
    assert len(data["peaks"]) == 200
    assert max(data["peaks"]) == pytest.approx(1.0, abs=1e-3)
    assert data["duration"] == pytest.approx(3.0, abs=0.1)


def test_spectrogram_is_png(wav_file):
    png = audio_service.spectrogram_png(wav_file)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png) > 1000


def test_spectrogram_of_silence_raises(audio_dir):
    import soundfile as sf

    silence_path = audio_dir / "silence.wav"
    sf.write(str(silence_path), np.zeros(16000, dtype=np.float32), 16000)
    with pytest.raises(ValidationAppError, match="silent"):
        audio_service.load_model_input(silence_path)


def test_stereo_is_downmixed(audio_dir):
    import soundfile as sf

    stereo_path = audio_dir / "stereo.wav"
    t = np.linspace(0, 2.0, 32000, endpoint=False)
    left = 0.3 * np.sin(2 * np.pi * 200 * t)
    right = 0.3 * np.sin(2 * np.pi * 210 * t)
    sf.write(str(stereo_path), np.stack([left, right], axis=1), 16000, subtype="PCM_16")

    info = audio_service.probe_audio(stereo_path)
    assert info.channels == 2
    waveform, rate = audio_service.load_model_input(stereo_path, 16000)
    assert waveform.ndim == 1
    assert rate == 16000
