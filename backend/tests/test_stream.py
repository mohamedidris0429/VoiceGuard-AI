"""Phase 4 - near-real-time chunked analysis tests."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from sqlalchemy import func, select

from app.ai.detector import Prediction
from app.core.config import settings
from app.services import stream_service

SAMPLE_RATE = 16000


@pytest.fixture(autouse=True)
def _clean_sessions():
    stream_service.reset_registry()
    yield
    stream_service.reset_registry()


@pytest.fixture()
def fake_detector(monkeypatch):
    class _Fake:
        scores = [0.2]
        calls = 0

        def predict(self, waveform, sample_rate):  # noqa: ANN001
            if waveform.size == 0:
                raise AssertionError("empty chunk passed to detector")
            _Fake.calls += 1
            score = self.scores.pop(0) if self.scores else 0.5
            predicted = "synthetic" if score >= 0.5 else "genuine"
            return Prediction(
                predicted_class=predicted,
                synthetic_probability=score,
                confidence=score if predicted == "synthetic" else 1.0 - score,
                model_id="test/stub-model",
                model_version="test/stub-model@stub",
                labels={"0": "real", "1": "fake"},
                windows_analyzed=1,
                window_seconds=4.0,
                window_scores=[score],
                inference_ms=4,
                threshold=0.5,
                parameters=1000,
            )

    fake = _Fake()
    monkeypatch.setattr(stream_service, "get_detector", lambda: fake)
    return fake


def _wav_bytes(seconds: float = 3.0, amplitude: float = 0.4) -> bytes:
    t = np.linspace(0.0, seconds, int(SAMPLE_RATE * seconds), endpoint=False)
    signal = (amplitude * np.sin(2 * np.pi * 170 * t)).astype(np.float32)
    buffer = io.BytesIO()
    sf.write(buffer, signal, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


def _start(client, headers, chunk_seconds: float = 3.0):
    return client.post(
        "/api/stream/sessions", json={"chunk_seconds": chunk_seconds}, headers=headers
    )


def _send(client, headers, session_id: str, data: bytes, *, index=None, name="chunk.wav"):
    form = {"chunk_index": str(index)} if index is not None else {}
    return client.post(
        f"/api/stream/sessions/{session_id}/chunks",
        files={"file": (name, data, "audio/wav")},
        data=form,
        headers=headers,
    )


# ------------------------------------------------------------------ lifecycle


def test_stream_requires_authentication(client):
    assert client.post("/api/stream/sessions", json={"chunk_seconds": 3}).status_code == 401
    assert client.get("/api/stream/sessions/abc").status_code == 401


def test_session_states_near_real_time_mode(client, register_user, auth_headers):
    user = register_user()
    response = _start(client, auth_headers(user))
    assert response.status_code == 201, response.text
    payload = response.json()

    assert payload["mode"] == "near_real_time_chunked"
    assert "not continuous" in payload["latency_note"].lower()
    assert "not a verified whole-file verdict" in payload["caveat"].lower()
    assert payload["status"] == "active"
    assert payload["chunk_seconds"] == 3.0
    assert payload["chunks"] == []


def test_chunk_seconds_are_bounded(client, register_user, auth_headers):
    user = register_user()
    assert _start(client, auth_headers(user), 0.2).status_code == 422
    assert _start(client, auth_headers(user), 30).status_code == 422


def test_chunk_is_scored_and_audio_is_not_retained(
    client, register_user, auth_headers, fake_detector
):
    user = register_user()
    session = _start(client, auth_headers(user)).json()
    fake_detector.scores = [0.73]

    response = _send(client, auth_headers(user), session["session_id"], _wav_bytes(3.0))
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["total_chunks"] == 1
    assert payload["scored_chunks"] == 1
    assert payload["average_score"] == pytest.approx(0.73)
    chunk = payload["chunks"][0]
    assert chunk["index"] == 0
    assert chunk["start_seconds"] == 0.0
    assert chunk["end_seconds"] == pytest.approx(3.0, abs=0.05)
    assert chunk["label"] == "synthetic"
    assert chunk["latency_ms"] >= 0
    assert chunk["model_version"] == "test/stub-model@stub"

    leftovers = list(Path(settings.tmp_dir).glob("live-*"))
    assert leftovers == [], "chunk audio must be deleted after scoring"

    # Nothing from live analysis is written to the database.
    from app.database.session import SessionLocal
    from app.models.analysis import AudioAnalysis

    with SessionLocal() as db:
        assert db.scalar(select(func.count(AudioAnalysis.id))) == 0


def test_chunks_must_arrive_in_order(client, register_user, auth_headers, fake_detector):
    user = register_user()
    session = _start(client, auth_headers(user)).json()

    response = _send(
        client, auth_headers(user), session["session_id"], _wav_bytes(2.0), index=1
    )
    assert response.status_code == 409
    assert response.json()["code"] == "chunk_out_of_order"

    first = _send(client, auth_headers(user), session["session_id"], _wav_bytes(2.0), index=0)
    assert first.status_code == 200
    second = _send(client, auth_headers(user), session["session_id"], _wav_bytes(2.0), index=1)
    assert second.status_code == 200
    assert [c["index"] for c in second.json()["chunks"]] == [0, 1]


def test_running_average_uses_scored_chunks_only(
    client, register_user, auth_headers, fake_detector
):
    user = register_user()
    session = _start(client, auth_headers(user)).json()
    fake_detector.scores = [0.2, 0.8]

    _send(client, auth_headers(user), session["session_id"], _wav_bytes(3.0))
    payload = _send(client, auth_headers(user), session["session_id"], _wav_bytes(3.0)).json()

    assert payload["scored_chunks"] == 2
    assert payload["average_score"] == pytest.approx(0.5)
    assert payload["duration_seconds"] == pytest.approx(6.0, abs=0.1)
    assert payload["chunks"][1]["start_seconds"] == pytest.approx(3.0)


def test_stopped_session_rejects_further_chunks(
    client, register_user, auth_headers, fake_detector
):
    user = register_user()
    session = _start(client, auth_headers(user)).json()
    _send(client, auth_headers(user), session["session_id"], _wav_bytes(2.0))

    stopped = client.post(
        f"/api/stream/sessions/{session['session_id']}/stop", headers=auth_headers(user)
    )
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopped"

    response = _send(client, auth_headers(user), session["session_id"], _wav_bytes(2.0))
    assert response.status_code == 409
    assert response.json()["code"] == "stream_session_closed"


def test_session_is_private_to_its_owner(
    client, register_user, auth_headers, fake_detector
):
    owner = register_user()
    session = _start(client, auth_headers(owner)).json()
    other = register_user()

    assert (
        client.get(
            f"/api/stream/sessions/{session['session_id']}", headers=auth_headers(other)
        ).status_code
        == 404
    )
    assert _send(client, auth_headers(other), session["session_id"], _wav_bytes(2.0)).status_code == 404
    assert (
        client.post(
            f"/api/stream/sessions/{session['session_id']}/stop", headers=auth_headers(other)
        ).status_code
        == 404
    )


def test_unknown_session_is_not_found(client, register_user, auth_headers):
    user = register_user()
    assert (
        client.get("/api/stream/sessions/does-not-exist", headers=auth_headers(user)).status_code
        == 404
    )


def test_session_cap_returns_429(client, register_user, auth_headers):
    user = register_user()
    for _ in range(stream_service.MAX_ACTIVE_SESSIONS):
        assert _start(client, auth_headers(user)).status_code == 201

    response = _start(client, auth_headers(user))
    assert response.status_code == 429
    assert response.json()["code"] == "too_many_sessions"


# --------------------------------------------------------------- chunk validation


def test_oversized_chunk_is_rejected(client, register_user, auth_headers, fake_detector):
    user = register_user()
    session = _start(client, auth_headers(user), 1.0).json()

    response = _send(client, auth_headers(user), session["session_id"], _wav_bytes(3.0))
    assert response.status_code == 422
    assert response.json()["code"] == "chunk_too_long"
    assert "3.0s" in response.json()["detail"]


def test_silent_chunk_is_rejected(client, register_user, auth_headers, fake_detector):
    user = register_user()
    session = _start(client, auth_headers(user)).json()
    silent = io.BytesIO()
    sf.write(silent, np.zeros(SAMPLE_RATE * 2, dtype=np.float32), SAMPLE_RATE, format="WAV")

    response = _send(client, auth_headers(user), session["session_id"], silent.getvalue())
    assert response.status_code == 422
    assert "silent" in response.json()["detail"].lower()


def test_corrupt_chunk_is_rejected_without_internal_details(
    client, register_user, auth_headers, fake_detector
):
    user = register_user()
    session = _start(client, auth_headers(user)).json()

    response = _send(
        client,
        auth_headers(user),
        session["session_id"],
        b"RIFF____WAVE" + b"garbage" * 40,
        name="broken.wav",
    )
    assert response.status_code in {415, 422}
    detail = response.json()["detail"]
    assert "Traceback" not in detail
    assert "\\" not in detail


def test_session_can_be_discarded(client, register_user, auth_headers):
    user = register_user()
    session = _start(client, auth_headers(user)).json()

    deleted = client.delete(
        f"/api/stream/sessions/{session['session_id']}", headers=auth_headers(user)
    )
    assert deleted.status_code == 200
    assert (
        client.get(
            f"/api/stream/sessions/{session['session_id']}", headers=auth_headers(user)
        ).status_code
        == 404
    )
