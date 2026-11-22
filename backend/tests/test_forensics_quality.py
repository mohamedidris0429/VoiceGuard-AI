"""Phase 3 - signal quality, metadata and per-segment signal measurements."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from app.core.config import settings
from app.services import forensic_service

SAMPLE_RATE = 16000


def _write(path: Path, signal: np.ndarray, sample_rate: int = SAMPLE_RATE) -> Path:
    sf.write(str(path), signal.astype(np.float32), sample_rate, subtype="PCM_16")
    return path


def _tone(seconds: float = 2.0, amplitude: float = 0.4) -> np.ndarray:
    t = np.linspace(0.0, seconds, int(SAMPLE_RATE * seconds), endpoint=False)
    return (amplitude * np.sin(2 * np.pi * 180 * t)).astype(np.float32)


def _upload(client, auth_headers, user, path: Path, content_type="audio/wav"):
    with open(path, "rb") as handle:
        files = {"file": (path.name, handle, content_type)}
        return client.post("/api/audio/upload", files=files, headers=auth_headers(user))


@pytest.fixture()
def fake_detector(monkeypatch):
    """Deterministic detector stub for segment planning paths (no real model)."""
    from app.ai.detector import Prediction
    from app.services import segment_service

    class _Fake:
        scores = [0.1, 0.2]

        def predict(self, waveform, sample_rate):  # noqa: ANN001
            score = self.scores.pop(0) if self.scores else 0.5
            return Prediction(
                predicted_class="synthetic" if score >= 0.5 else "genuine",
                synthetic_probability=score,
                confidence=score if score >= 0.5 else 1.0 - score,
                model_id="test/stub-model",
                model_version="test/stub-model@stub",
                labels={"0": "real", "1": "fake"},
                windows_analyzed=1,
                window_seconds=4.0,
                window_scores=[score],
                inference_ms=3,
                threshold=0.5,
                parameters=1000,
            )

    fake = _Fake()
    monkeypatch.setattr(segment_service, "get_detector", lambda: fake)
    return fake


# ---------------------------------------------------------------- unit: quality


def test_quality_measurements_are_physical():
    quality = forensic_service.measure_quality(_tone(2.0, 0.5), SAMPLE_RATE)

    assert -6.5 < quality["peak_dbfs"] < -5.5  # 0.5 amplitude ~= -6.02 dBFS
    assert quality["rms_dbfs"] < quality["peak_dbfs"]
    assert quality["crest_factor_db"] > 0
    assert 0.0 <= quality["clipping_ratio"] <= 1.0
    assert abs(quality["dc_offset"]) < 1e-3
    assert quality["effective_bandwidth_hz"] is not None
    assert quality["nyquist_hz"] == SAMPLE_RATE / 2
    assert quality["note"]
    assert quality["observations"], "every quality report needs at least one observation"


def test_quality_flags_digital_silence():
    quality = forensic_service.measure_quality(np.zeros(SAMPLE_RATE, dtype=np.float32), SAMPLE_RATE)
    codes = {item["code"] for item in quality["observations"]}
    assert "silent" in codes
    assert quality["peak_dbfs"] <= -100


def test_quality_detects_clipping_and_dc_offset():
    clipped = np.clip(_tone(1.0, 2.0), -1.0, 1.0)
    quality = forensic_service.measure_quality(clipped, SAMPLE_RATE)
    codes = {item["code"] for item in quality["observations"]}
    assert quality["clipping_ratio"] > 0.01
    assert "clipping" in codes

    offset = _tone(1.0, 0.3) + 0.2
    offset_quality = forensic_service.measure_quality(offset, SAMPLE_RATE)
    assert offset_quality["dc_offset"] > 0.15
    assert any(item["code"] == "dc_offset" for item in offset_quality["observations"])


def test_quality_rejects_invalid_samples():
    from app.services.audio_service import AudioProcessingError

    with pytest.raises(AudioProcessingError):
        forensic_service.measure_quality(np.array([0.1, np.nan, 0.2], dtype=np.float32), SAMPLE_RATE)


# ------------------------------------------------------------ API: metadata + quality


def test_forensics_reports_quality_and_metadata(
    client, register_user, auth_headers, upload_audio, wav_file
):
    user = register_user()
    analysis = upload_audio(user, wav_file)

    payload = client.get(
        f"/api/forensics/{analysis['id']}", headers=auth_headers(user)
    ).json()

    quality = payload["quality"]
    for field in (
        "peak_dbfs",
        "rms_dbfs",
        "crest_factor_db",
        "clipping_ratio",
        "dc_offset",
        "snr_estimate_db",
        "silence_ratio",
        "observations",
        "note",
    ):
        assert field in quality, field
    assert quality["observations"][0]["severity"] in {"info", "caution", "warning"}
    assert quality["observations"][0]["detail"]
    assert payload["audio"]["bit_depth"] == 16
    assert payload["audio"]["average_bitrate_kbps"] == pytest.approx(
        16000 * 16 / 1000, rel=0.15
    )


def test_silent_recording_is_flagged_not_scored(
    client, register_user, auth_headers, audio_dir
):
    user = register_user()
    path = _write(audio_dir / "silence.wav", np.zeros(SAMPLE_RATE * 2, dtype=np.float32))
    upload = _upload(client, auth_headers, user, path)
    assert upload.status_code == 201, upload.text
    analysis = upload.json()

    response = client.get(f"/api/forensics/{analysis['id']}", headers=auth_headers(user))
    assert response.status_code == 200, response.text
    codes = {item["code"] for item in response.json()["quality"]["observations"]}
    assert "silent" in codes

    # Segment signal measurement refuses to invent numbers for silence.
    segment_response = client.get(
        f"/api/forensics/{analysis['id']}/segment-signal", headers=auth_headers(user)
    )
    assert segment_response.status_code == 422
    assert "silent" in segment_response.json()["detail"].lower()


# ------------------------------------------------------- segment signal summaries


def test_segment_signal_uses_default_plan_before_analysis(
    client, register_user, auth_headers, audio_dir
):
    user = register_user()
    t = np.linspace(0.0, 4.5, int(SAMPLE_RATE * 4.5), endpoint=False)
    path = _write(audio_dir / "plan_only.wav", 0.3 * np.sin(2 * np.pi * 150 * t))
    analysis = _upload(client, auth_headers, user, path).json()

    response = client.get(
        f"/api/forensics/{analysis['id']}/segment-signal", headers=auth_headers(user)
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["computed"] is False
    assert payload["total_segments"] == len(payload["segments"]) > 0
    assert payload["segments"][0]["start_seconds"] == 0.0
    assert payload["segments"][-1]["end_seconds"] <= 4.51
    assert all(segment["end_seconds"] <= 4.51 for segment in payload["segments"])
    assert payload["quality"]["observations"]
    assert payload["note"]

    measured = [s for s in payload["segments"] if s["rms_dbfs"] is not None]
    assert measured, "expected measurable spans"
    assert all(s["peak_dbfs"] >= s["rms_dbfs"] for s in measured)


def test_segment_signal_reuses_stored_segments(
    client, register_user, auth_headers, upload_audio, wav_file, fake_detector
):
    user = register_user()
    analysis = upload_audio(user, wav_file)
    fake_detector.scores = [0.1, 0.2]

    stored = client.post(
        f"/api/forensics/{analysis['id']}/segments?window_seconds=2&hop_seconds=1",
        headers=auth_headers(user),
    ).json()

    response = client.get(
        f"/api/forensics/{analysis['id']}/segment-signal", headers=auth_headers(user)
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["computed"] is True
    assert payload["total_segments"] == len(stored["segments"])
    assert [s["index"] for s in payload["segments"]] == [s["index"] for s in stored["segments"]]
    for signal_segment, model_segment in zip(payload["segments"], stored["segments"]):
        assert signal_segment["start_seconds"] == model_segment["start_seconds"]
        assert signal_segment["end_seconds"] == model_segment["end_seconds"]
        assert signal_segment["state"] == model_segment["state"]


def test_segment_signal_requires_authentication(client):
    assert client.get("/api/forensics/1/segment-signal").status_code == 401


def test_segment_signal_rejects_other_users_record(
    client, register_user, auth_headers, upload_audio, wav_file
):
    owner = register_user()
    analysis = upload_audio(owner, wav_file)
    other = register_user()
    response = client.get(
        f"/api/forensics/{analysis['id']}/segment-signal", headers=auth_headers(other)
    )
    assert response.status_code == 404


def test_segment_signal_missing_file_returns_gone(
    client, register_user, auth_headers, upload_audio, wav_file
):
    user = register_user()
    analysis = upload_audio(user, wav_file)
    audio_root = Path(settings.audio_dir) / str(user["user"]["id"])
    for stored in audio_root.glob("*"):
        stored.unlink()

    response = client.get(
        f"/api/forensics/{analysis['id']}/segment-signal", headers=auth_headers(user)
    )
    assert response.status_code == 410


def test_corrupt_stored_audio_returns_clean_422(
    client, register_user, auth_headers, upload_audio, wav_file
):
    user = register_user()
    analysis = upload_audio(user, wav_file)
    audio_root = Path(settings.audio_dir) / str(user["user"]["id"])
    stored = next(audio_root.glob("*"))
    stored.write_bytes(b"RIFF____WAVEjunkjunkjunk")

    response = client.get(
        f"/api/forensics/{analysis['id']}/segment-signal", headers=auth_headers(user)
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "decoded" in detail.lower() or "measurement" in detail.lower()
    assert "Traceback" not in detail
