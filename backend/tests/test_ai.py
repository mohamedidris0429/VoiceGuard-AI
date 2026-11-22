"""AI detector logic tests plus an opt-in real-model integration test."""

from __future__ import annotations

import os

import numpy as np
import pytest

from app.ai import detector as detector_module
from app.ai.detector import VoiceDetector, _find_synthetic_index, _sanitize_error
from app.core.errors import ModelUnavailableError


class _FakeTensorModule:
    """Minimal stand-in so the aggregation logic can be tested without torch."""

    class inference_mode:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False


def test_find_synthetic_index_prefers_spoof_labels():
    assert _find_synthetic_index({0: "real", 1: "fake"}) == 1
    assert _find_synthetic_index({0: "bonafide", 1: "spoof"}) == 1
    assert _find_synthetic_index({0: "spoof", 1: "bonafide"}) == 0
    assert _find_synthetic_index({0: "genuine", 1: "synthetic"}) == 1
    assert _find_synthetic_index({0: "yes", 1: "no"}) is None


def test_sanitize_error_hides_paths():
    raw = RuntimeError("Could not load C:\\Users\\someone\\models\\weights.bin from cache")
    cleaned = _sanitize_error(raw)
    assert "C:\\Users" not in cleaned
    assert "<path>" in cleaned


def test_status_reports_not_loaded():
    fresh = VoiceDetector()
    status = fresh.status()
    assert status["loaded"] is False
    assert status["available"] is False
    assert status["model_id"]


def test_windows_cover_whole_file_and_are_bounded(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "model_window_seconds", 1.0)
    monkeypatch.setattr(settings, "model_max_windows", 3)
    voice = VoiceDetector()
    waveform = np.zeros(10 * 16000, dtype=np.float32)
    windows = voice._windows(waveform, 16000)
    assert len(windows) == 3
    assert all(window.size == 16000 for window in windows)


def test_short_audio_is_padded(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "model_window_seconds", 4.0)
    voice = VoiceDetector()
    windows = voice._windows(np.ones(16000, dtype=np.float32), 16000)
    assert len(windows) == 1
    assert windows[0].size == 64000


def test_unavailable_model_raises_clear_error(monkeypatch):
    voice = VoiceDetector()
    monkeypatch.setattr(voice, "_load", lambda: (_ for _ in ()).throw(RuntimeError("no weights")))
    with pytest.raises(ModelUnavailableError) as excinfo:
        voice._ensure_loaded()
    assert "unavailable" in str(excinfo.value).lower()
    assert "no weights" in voice.status()["detail"]


@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get("VOICEGUARD_RUN_MODEL_TESTS") != "1",
    reason="set VOICEGUARD_RUN_MODEL_TESTS=1 to run real inference",
)
def test_real_model_inference(wav_file):
    from app.services.audio_service import load_model_input

    detector = detector_module.get_detector()
    waveform, sample_rate = load_model_input(wav_file, 16000)
    prediction = detector.predict(waveform, sample_rate)

    assert prediction.predicted_class in {"genuine", "synthetic"}
    assert 0.0 <= prediction.synthetic_probability <= 1.0
    assert 0.5 <= prediction.confidence <= 1.0
    assert prediction.windows_analyzed >= 1
    assert prediction.model_version.startswith("Vansh180/")
    assert prediction.parameters and prediction.parameters > 1_000_000
