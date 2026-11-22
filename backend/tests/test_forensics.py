"""Phase 1 forensics workspace endpoint tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from app.core.config import settings

SAMPLE_RATE = 16000


def _write_stereo_wav(path: Path, seconds: float = 2.0) -> Path:
    rng = np.random.default_rng(3)
    t = np.linspace(0.0, seconds, int(SAMPLE_RATE * seconds), endpoint=False)
    left = 0.3 * np.sin(2 * np.pi * 180 * t)
    right = 0.2 * np.sin(2 * np.pi * 240 * t)
    stereo = np.stack([left, right], axis=1) + rng.normal(0, 0.002, (t.size, 2))
    sf.write(str(path), stereo.astype(np.float32), SAMPLE_RATE, subtype="PCM_16")
    return path


def _upload(client, auth_headers, user, path: Path, filename=None, content_type="audio/wav"):
    with open(path, "rb") as handle:
        files = {"file": (filename or path.name, handle, content_type)}
        return client.post("/api/audio/upload", files=files, headers=auth_headers(user))


def test_forensics_requires_authentication(client):
    assert client.get("/api/forensics/1").status_code == 401


def test_forensics_rejects_other_users_record(
    client, register_user, auth_headers, upload_audio, wav_file
):
    owner = register_user()
    analysis = upload_audio(owner, wav_file)
    other = register_user()
    response = client.get(f"/api/forensics/{analysis['id']}", headers=auth_headers(other))
    assert response.status_code == 404


def test_forensics_reports_wav_signal_data(
    client, register_user, auth_headers, upload_audio, wav_file
):
    user = register_user()
    analysis = upload_audio(user, wav_file)

    response = client.get(f"/api/forensics/{analysis['id']}", headers=auth_headers(user))
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["analysis_id"] == analysis["id"]
    assert payload["audio"]["sample_rate_hz"] == SAMPLE_RATE
    assert payload["audio"]["channels"] == 1
    assert payload["audio"]["channel_layout"] == "mono"
    assert abs(payload["audio"]["duration_seconds"] - 3.0) < 0.05
    assert payload["audio"]["nyquist_hz"] == SAMPLE_RATE / 2
    assert payload["audio"]["frames"] > 0

    assert payload["waveform"]["peaks"], "waveform peaks missing"
    assert payload["waveform"]["buckets"] == len(payload["waveform"]["peaks"])

    signal = payload["signal"]
    assert len(signal["rms_timeline"]["times"]) == len(signal["rms_timeline"]["rms"])
    assert 0 < len(signal["rms_timeline"]["rms"]) <= 160
    assert signal["band_energy"], "band energy missing"
    assert abs(sum(band["share"] for band in signal["band_energy"]) - 1.0) < 0.02
    assert all(0.0 <= band["share"] <= 1.0 for band in signal["band_energy"])
    assert signal["note"]

    assert payload["evidence_note"]
    assert payload["disclaimer"]
    assert payload["model"]["status"] == "pending"
    assert payload["model"]["predicted_class"] is None


def test_forensics_supports_stereo_recordings(
    client, register_user, auth_headers, audio_dir
):
    user = register_user()
    path = _write_stereo_wav(audio_dir / "stereo.wav")
    upload = _upload(client, auth_headers, user, path)
    assert upload.status_code == 201, upload.text
    analysis = upload.json()
    assert analysis["channels"] == 2

    response = client.get(f"/api/forensics/{analysis['id']}", headers=auth_headers(user))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["audio"]["channels"] == 2
    assert payload["audio"]["channel_layout"] == "stereo"
    assert payload["waveform"]["peaks"]


def test_forensics_supports_mp3(client, register_user, auth_headers, mp3_file):
    user = register_user()
    upload = _upload(client, auth_headers, user, mp3_file, content_type="audio/mpeg")
    assert upload.status_code == 201, upload.text
    analysis = upload.json()

    response = client.get(f"/api/forensics/{analysis['id']}", headers=auth_headers(user))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["file_format"] == "mp3"
    assert payload["waveform"]["peaks"]
    assert payload["signal"]["band_energy"]


def test_invalid_recording_is_rejected_on_upload(
    client, register_user, auth_headers, audio_dir
):
    user = register_user()
    path = audio_dir / "broken.wav"
    path.write_bytes(b"RIFF" + (36).to_bytes(4, "little") + b"WAVE" + b"not-audio" * 32)

    response = _upload(client, auth_headers, user, path)
    assert response.status_code == 422, response.text
    detail = response.json()["detail"].lower()
    assert "decoded" in detail or "audio" in detail


def test_forensics_media_streams_original_audio(
    client, register_user, auth_headers, upload_audio, wav_file
):
    user = register_user()
    analysis = upload_audio(user, wav_file)

    response = client.get(f"/api/forensics/{analysis['id']}/media", headers=auth_headers(user))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/")
    assert response.content[:4] == b"RIFF"

    assert client.get(f"/api/forensics/{analysis['id']}/media").status_code == 401


def test_forensics_missing_file_returns_gone(
    client, register_user, auth_headers, upload_audio, wav_file
):
    user = register_user()
    analysis = upload_audio(user, wav_file)

    audio_root = Path(settings.audio_dir) / str(user["user"]["id"])
    for stored in audio_root.glob("*"):
        stored.unlink()

    response = client.get(f"/api/forensics/{analysis['id']}", headers=auth_headers(user))
    assert response.status_code == 410
