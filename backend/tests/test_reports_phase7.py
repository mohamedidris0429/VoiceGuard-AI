"""Phase 7 - PDF reports must reflect stored data, scope and limitations."""

from __future__ import annotations

import base64
import re
import zlib

import numpy as np
import pytest
import soundfile as sf

from app.ai.detector import Prediction
from app.services import segment_service

SAMPLE_RATE = 16000


def pdf_text(data: bytes) -> str:
    """Extract literal text from ReportLab page streams (Flate or plain)."""
    chunks: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        raw = match.group(1).strip()
        if raw.endswith(b"~>"):  # ReportLab default: ASCII85 then Flate
            try:
                raw = base64.a85decode(raw, adobe=True)
            except ValueError:
                pass
        try:
            raw = zlib.decompress(raw)
        except zlib.error:
            pass
        chunks.append(raw.decode("latin-1", "ignore"))
    # ReportLab emits one string per word/line fragment; normalise whitespace.
    return " ".join(" ".join(chunks).split())


@pytest.fixture()
def fake_detector(monkeypatch):
    class _Fake:
        scores = [0.2, 0.2]

        def predict(self, waveform, sample_rate):  # noqa: ANN001
            score = self.scores.pop(0) if self.scores else 0.2
            return Prediction(
                predicted_class="synthetic" if score >= 0.5 else "genuine",
                synthetic_probability=score,
                confidence=score if score >= 0.5 else 1 - score,
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


def _write_mixed(path, seconds=4.0, silent_tail=2.0):
    t = np.linspace(0.0, seconds, int(SAMPLE_RATE * seconds), endpoint=False)
    signal = (0.3 * np.sin(2 * np.pi * 150 * t)).astype(np.float32)
    signal[int((seconds - silent_tail) * SAMPLE_RATE) :] = 0.0
    sf.write(str(path), signal, SAMPLE_RATE, subtype="PCM_16")
    return path


def _completed(client, user, auth_headers, upload_audio, path):
    analysis = upload_audio(user, path)
    result = client.post(
        "/api/audio/analyze", json={"analysis_id": analysis["id"]}, headers=auth_headers(user)
    )
    assert result.status_code == 200, result.text
    assert result.json()["analysis_status"] == "completed"
    return result.json()


def test_report_includes_partial_segment_analysis_and_quality(
    client, register_user, auth_headers, upload_audio, audio_dir, fake_detector, stub_detector
):
    user = register_user()
    path = _write_mixed(audio_dir / "report_partial.wav")
    analysis = _completed(client, user, auth_headers, upload_audio, path)

    segments = client.post(
        f"/api/forensics/{analysis['id']}/segments?window_seconds=1&hop_seconds=1",
        headers=auth_headers(user),
    )
    assert segments.status_code == 200, segments.text
    assert segments.json()["aggregate"]["whole_file_reliable"] is False

    response = client.get(f"/api/reports/{analysis['id']}/download", headers=auth_headers(user))
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    pdf = response.content
    assert pdf.startswith(b"%PDF-")

    text = pdf_text(pdf)
    assert "Window-by-window analysis" in text
    assert "Partial" in text
    assert "Coverage" in text
    assert "Recording-quality observations" in text
    assert "not a whole-file conclusion" in text
    assert "Limitations and disclaimer" in text
    assert "Window scores are independent probabilistic model outputs" in text


def test_report_without_stored_media_still_downloads(
    client, register_user, auth_headers, upload_audio, wav_file, stub_detector
):
    from pathlib import Path

    from app.core.config import settings

    user = register_user()
    analysis = _completed(client, user, auth_headers, upload_audio, wav_file)

    audio_root = Path(settings.audio_dir) / str(user["user"]["id"])
    for stored in audio_root.glob("*"):
        stored.unlink()

    response = client.get(f"/api/reports/{analysis['id']}/download", headers=auth_headers(user))
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF-")
    text = pdf_text(response.content)
    assert "Recording-quality observations" not in text
    assert "Limitations and disclaimer" in text


def test_report_is_not_available_for_other_users(
    client, register_user, auth_headers, upload_audio, wav_file, stub_detector
):
    owner = register_user()
    analysis = _completed(client, owner, auth_headers, upload_audio, wav_file)
    other = register_user()

    response = client.get(f"/api/reports/{analysis['id']}/download", headers=auth_headers(other))
    assert response.status_code == 404
