"""Pytest configuration.

Tests run against a throwaway SQLite database by default (fast, zero setup).
Set ``TEST_DATABASE_URL`` to exercise the same suite against PostgreSQL, e.g.:

    set TEST_DATABASE_URL=postgresql+psycopg://voiceguard:voiceguard@127.0.0.1:5433/voiceguard_test
    pytest
"""

from __future__ import annotations

import os
import secrets
import shutil
import tempfile
import uuid
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

_TMP_ROOT = Path(tempfile.mkdtemp(prefix="voiceguard-tests-"))
_TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()

if _TEST_DATABASE_URL:
    os.environ["DATABASE_URL"] = _TEST_DATABASE_URL
else:
    os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP_ROOT / 'test.db').as_posix()}"

os.environ["STORAGE_DIR"] = str(_TMP_ROOT / "storage")
os.environ["SECRET_KEY"] = secrets.token_urlsafe(48)
os.environ["MODEL_OFFLINE"] = "1"
os.environ["RATE_LIMIT_AUTH"] = "1000/60"
os.environ["RATE_LIMIT_ANALYSIS"] = "1000/60"
os.environ.setdefault("ENVIRONMENT", "test")

SAMPLE_RATE = 16000


def _write_speech_like_wav(path: Path, seconds: float = 3.0, seed: int = 0) -> Path:
    """Harmonic 'voiced' signal with mild noise - deterministic and tiny."""
    rng = np.random.default_rng(seed)
    t = np.linspace(0.0, seconds, int(SAMPLE_RATE * seconds), endpoint=False)
    base = 140.0 + 10.0 * np.sin(2 * np.pi * 0.7 * t)
    signal = 0.28 * np.sin(2 * np.pi * base * t)
    signal += 0.12 * np.sin(2 * np.pi * 2 * base * t)
    signal += 0.06 * np.sin(2 * np.pi * 3 * base * t)
    envelope = 0.6 + 0.4 * np.sin(2 * np.pi * 1.6 * t) ** 2
    signal = signal * envelope + rng.normal(0, 0.004, t.size)
    signal = (0.9 * signal / max(1e-9, np.max(np.abs(signal)))).astype(np.float32)
    sf.write(str(path), signal, SAMPLE_RATE, subtype="PCM_16")
    return path


@pytest.fixture(scope="session", autouse=True)
def _schema():
    from app.database.base import Base
    from app.database.session import engine
    import app.models  # noqa: F401  (register metadata)

    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    shutil.rmtree(_TMP_ROOT, ignore_errors=True)


@pytest.fixture(autouse=True)
def _clean_state():
    from app.core.rate_limit import limiter
    from app.database.base import Base
    from app.database.session import engine

    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    limiter.reset()
    yield


@pytest.fixture(scope="session")
def audio_dir() -> Path:
    directory = _TMP_ROOT / "fixtures"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


@pytest.fixture(scope="session")
def wav_file(audio_dir: Path) -> Path:
    return _write_speech_like_wav(audio_dir / "sample_voice.wav", 3.0)


@pytest.fixture(scope="session")
def second_wav_file(audio_dir: Path) -> Path:
    return _write_speech_like_wav(audio_dir / "sample_voice_b.wav", 2.0, seed=7)


@pytest.fixture(scope="session")
def short_wav_file(audio_dir: Path) -> Path:
    return _write_speech_like_wav(audio_dir / "too_short.wav", 0.2)


@pytest.fixture(scope="session")
def mp3_file(audio_dir: Path) -> Path:
    """MP3 fixture; skipped when libsndfile lacks an MP3 encoder."""
    path = audio_dir / "sample_voice.mp3"
    signal, _ = sf.read(str(_write_speech_like_wav(audio_dir / "_tmp_for_mp3.wav", 2.0)))
    try:
        sf.write(str(path), signal, SAMPLE_RATE, format="MP3")
    except Exception:  # pragma: no cover - environment dependent
        pytest.skip("libsndfile build has no MP3 encoder")
    return path


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def register_user(client):
    def _register(email: str | None = None, password: str = "Str0ngPass123", name: str = "Test User"):
        email = email or f"user-{uuid.uuid4().hex[:10]}@example.com"
        response = client.post(
            "/api/auth/register",
            json={"name": name, "email": email, "password": password},
        )
        assert response.status_code == 201, response.text
        payload = response.json()
        payload["password"] = password
        payload["email_used"] = email
        return payload

    return _register


@pytest.fixture()
def auth_headers():
    def _headers(user: dict) -> dict:
        return {"Authorization": f"Bearer {user['access_token']}"}

    return _headers


@pytest.fixture()
def stub_detector(monkeypatch):
    """Replace the real model with a deterministic stub (unit tests stay fast)."""
    from app.ai.detector import Prediction
    from app.services import analysis_service

    class _FakeDetector:
        def __init__(self, score: float = 0.18):
            self.score = score

        def predict(self, waveform, sample_rate):  # noqa: ANN001
            if waveform.size == 0:
                raise AssertionError("empty waveform passed to detector")
            predicted = "synthetic" if self.score >= 0.5 else "genuine"
            confidence = self.score if predicted == "synthetic" else 1.0 - self.score
            return Prediction(
                predicted_class=predicted,
                synthetic_probability=self.score,
                confidence=confidence,
                model_id="test/stub-model",
                model_version="test/stub-model@stub",
                labels={"0": "real", "1": "fake"},
                windows_analyzed=1,
                window_seconds=4.0,
                window_scores=[self.score],
                inference_ms=5,
                threshold=0.5,
                parameters=1234,
            )

    fake = _FakeDetector()
    monkeypatch.setattr(analysis_service, "get_detector", lambda: fake)
    return fake


@pytest.fixture()
def upload_audio(client, auth_headers):
    """Upload a WAV file and return the pending analysis payload."""

    def _upload(user: dict, path: Path, filename: str | None = None):
        with open(path, "rb") as handle:
            files = {"file": (filename or path.name, handle, "audio/wav")}
            response = client.post("/api/audio/upload", files=files, headers=auth_headers(user))
        assert response.status_code == 201, response.text
        return response.json()

    return _upload
