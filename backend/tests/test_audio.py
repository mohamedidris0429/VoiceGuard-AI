"""Audio upload, validation and analysis pipeline tests."""

from __future__ import annotations

import io


def test_upload_valid_wav(client, register_user, auth_headers, wav_file):
    user = register_user()
    with open(wav_file, "rb") as handle:
        response = client.post(
            "/api/audio/upload",
            files={"file": ("my recording.wav", handle, "audio/wav")},
            headers=auth_headers(user),
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["analysis_status"] == "pending"
    assert body["filename"] == "my recording.wav"
    assert body["file_format"] == "wav"
    assert body["channels"] == 1
    assert body["sample_rate"] == 16000
    assert 2.9 <= body["audio_duration"] <= 3.1
    # Storage paths must never be exposed to clients.
    assert "stored_file_reference" not in body


def test_upload_requires_auth(client, wav_file):
    with open(wav_file, "rb") as handle:
        response = client.post(
            "/api/audio/upload", files={"file": ("a.wav", handle, "audio/wav")}
        )
    assert response.status_code == 401


def test_upload_rejects_unsupported_extension(client, register_user, auth_headers):
    user = register_user()
    response = client.post(
        "/api/audio/upload",
        files={"file": ("notes.txt", io.BytesIO(b"hello there"), "text/plain")},
        headers=auth_headers(user),
    )
    assert response.status_code == 415


def test_upload_rejects_wrong_content_for_extension(client, register_user, auth_headers):
    user = register_user()
    response = client.post(
        "/api/audio/upload",
        files={"file": ("fake.wav", io.BytesIO(b"this is definitely not audio"), "audio/wav")},
        headers=auth_headers(user),
    )
    assert response.status_code == 415
    assert "valid WAV or MP3" in response.json()["detail"]


def test_upload_rejects_mp3_content_declared_as_wav(client, register_user, auth_headers):
    user = register_user()
    mp3_like = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 128
    response = client.post(
        "/api/audio/upload",
        files={"file": ("mismatch.wav", io.BytesIO(mp3_like), "audio/wav")},
        headers=auth_headers(user),
    )
    assert response.status_code == 415
    assert "does not match" in response.json()["detail"]


def test_upload_rejects_empty_file(client, register_user, auth_headers):
    user = register_user()
    response = client.post(
        "/api/audio/upload",
        files={"file": ("empty.wav", io.BytesIO(b""), "audio/wav")},
        headers=auth_headers(user),
    )
    assert response.status_code == 415


def test_upload_rejects_too_short_audio(client, register_user, auth_headers, short_wav_file):
    user = register_user()
    with open(short_wav_file, "rb") as handle:
        response = client.post(
            "/api/audio/upload",
            files={"file": (short_wav_file.name, handle, "audio/wav")},
            headers=auth_headers(user),
        )
    assert response.status_code == 422
    assert "too short" in response.json()["detail"].lower()


def test_upload_rejects_oversized_file(client, register_user, auth_headers, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "max_upload_mb", 1)
    user = register_user()
    payload = b"RIFF" + b"\x00" * (1024 * 1024 + 256 * 1024) + b"WAVE"
    response = client.post(
        "/api/audio/upload",
        files={"file": ("big.wav", io.BytesIO(payload), "audio/wav")},
        headers=auth_headers(user),
    )
    assert response.status_code == 413


def test_upload_mp3(client, register_user, auth_headers, mp3_file):
    user = register_user()
    with open(mp3_file, "rb") as handle:
        response = client.post(
            "/api/audio/upload",
            files={"file": (mp3_file.name, handle, "audio/mpeg")},
            headers=auth_headers(user),
        )
    if response.status_code == 415 and "decode" in response.json()["detail"].lower():
        import pytest

        pytest.skip("libsndfile build cannot decode MP3 in this environment")
    assert response.status_code == 201, response.text
    assert response.json()["file_format"] == "mp3"


def test_analyze_with_stub_model(client, register_user, auth_headers, wav_file, stub_detector):
    user = register_user()
    upload = client.post(
        "/api/audio/upload",
        files={"file": ("voice.wav", open(wav_file, "rb"), "audio/wav")},
        headers=auth_headers(user),
    )
    analysis_id = upload.json()["id"]

    response = client.post(
        "/api/audio/analyze",
        json={"analysis_id": analysis_id},
        headers=auth_headers(user),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["analysis_status"] == "completed"
    assert body["predicted_class"] == "genuine"
    assert 0.0 <= body["model_score"] <= 1.0
    assert body["model_version"]
    assert body["model_details"]["windows_analyzed"] >= 1
    assert body["audio_features"]["spectral_centroid_hz"] > 0
    assert body["analysis_duration_ms"] is not None


def test_analyze_is_idempotent(client, register_user, auth_headers, wav_file, stub_detector):
    user = register_user()
    upload = client.post(
        "/api/audio/upload",
        files={"file": ("voice.wav", open(wav_file, "rb"), "audio/wav")},
        headers=auth_headers(user),
    )
    analysis_id = upload.json()["id"]
    first = client.post(
        "/api/audio/analyze", json={"analysis_id": analysis_id}, headers=auth_headers(user)
    ).json()
    second = client.post(
        "/api/audio/analyze", json={"analysis_id": analysis_id}, headers=auth_headers(user)
    ).json()
    assert first["model_score"] == second["model_score"]
    assert second["analysis_status"] == "completed"


def test_analyze_records_unavailable_when_model_fails(
    client, register_user, auth_headers, wav_file, monkeypatch
):
    from app.core.errors import ModelUnavailableError
    from app.services import analysis_service

    class _Broken:
        def predict(self, waveform, sample_rate):  # noqa: ANN001
            raise ModelUnavailableError("AI detection is unavailable: weights missing.")

    monkeypatch.setattr(analysis_service, "get_detector", lambda: _Broken())

    user = register_user()
    upload = client.post(
        "/api/audio/upload",
        files={"file": ("voice.wav", open(wav_file, "rb"), "audio/wav")},
        headers=auth_headers(user),
    )
    analysis_id = upload.json()["id"]
    response = client.post(
        "/api/audio/analyze", json={"analysis_id": analysis_id}, headers=auth_headers(user)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["analysis_status"] == "unavailable"
    assert body["predicted_class"] is None
    assert body["model_score"] is None
    assert "unavailable" in body["failure_reason"].lower()


def test_waveform_and_spectrogram(client, register_user, auth_headers, wav_file, stub_detector):
    user = register_user()
    upload = client.post(
        "/api/audio/upload",
        files={"file": ("voice.wav", open(wav_file, "rb"), "audio/wav")},
        headers=auth_headers(user),
    )
    analysis_id = upload.json()["id"]

    waveform = client.get(f"/api/audio/{analysis_id}/waveform", headers=auth_headers(user))
    assert waveform.status_code == 200
    peaks = waveform.json()["peaks"]
    assert len(peaks) >= 32
    assert all(0.0 <= value <= 1.0 for value in peaks)

    spectrogram = client.get(f"/api/audio/{analysis_id}/spectrogram", headers=auth_headers(user))
    assert spectrogram.status_code == 200
    assert spectrogram.headers["content-type"] == "image/png"
    assert spectrogram.content.startswith(b"\x89PNG")


def test_delete_analysis_removes_record_and_file(
    client, register_user, auth_headers, wav_file, stub_detector
):
    from app.database.session import SessionLocal
    from app.models.analysis import AudioAnalysis
    from app.services.storage_service import audio_path_for

    user = register_user()
    upload = client.post(
        "/api/audio/upload",
        files={"file": ("voice.wav", open(wav_file, "rb"), "audio/wav")},
        headers=auth_headers(user),
    )
    analysis_id = upload.json()["id"]

    with SessionLocal() as session:
        reference = session.get(AudioAnalysis, analysis_id).stored_file_reference
    path = audio_path_for(reference)
    assert path.exists()

    response = client.delete(f"/api/audio/{analysis_id}", headers=auth_headers(user))
    assert response.status_code == 200
    assert not path.exists()

    with SessionLocal() as session:
        assert session.get(AudioAnalysis, analysis_id) is None

    assert client.get(f"/api/audio/{analysis_id}", headers=auth_headers(user)).status_code == 404


def test_upload_limits_endpoint(client):
    response = client.get("/api/audio/limits/info")
    assert response.status_code == 200
    body = response.json()
    assert body["allowed_formats"] == ["mp3", "wav"]
    assert body["max_upload_mb"] > 0
