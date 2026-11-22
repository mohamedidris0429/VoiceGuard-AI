"""Phase 8 - security headers, rate limiting and upload validation regressions."""

from __future__ import annotations

from app.core.config import settings


def test_security_headers_are_present(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cross-origin-opener-policy"] == "same-origin"
    assert response.headers["x-permitted-cross-domain-policies"] == "none"
    assert "microphone=(self)" in response.headers["permissions-policy"]
    assert response.headers["cache-control"] == "no-store"


def test_unknown_extension_is_rejected(client, register_user, auth_headers):
    user = register_user()
    response = client.post(
        "/api/audio/upload",
        files={"file": ("payload.exe", b"MZ\x90\x00binary", "application/octet-stream")},
        headers=auth_headers(user),
    )
    assert response.status_code == 415
    assert response.json()["code"] == "unsupported_format"


def test_content_must_match_extension(client, register_user, auth_headers):
    user = register_user()
    response = client.post(
        "/api/audio/upload",
        files={"file": ("fake.wav", b"ID3\x03\x00\x00\x00" + b"\x00" * 40, "audio/wav")},
        headers=auth_headers(user),
    )
    assert response.status_code == 415
    assert response.json()["code"] == "format_mismatch"


def test_segment_endpoint_is_rate_limited(
    client, register_user, auth_headers, upload_audio, wav_file, monkeypatch
):
    user = register_user()
    analysis = upload_audio(user, wav_file)
    # The upload already consumed one slot in the shared analysis budget.
    monkeypatch.setattr(settings, "rate_limit_analysis", "2/60")

    url = f"/api/forensics/{analysis['id']}/segments?window_seconds=2&hop_seconds=2"
    first = client.post(url, headers=auth_headers(user))
    second = client.post(url, headers=auth_headers(user))

    assert first.status_code in {200, 409, 503}  # model may be unavailable offline
    assert second.status_code == 429
    assert second.json()["code"] == "rate_limited"


def test_authentication_errors_do_not_leak_details(client):
    response = client.get("/api/audio/1")
    assert response.status_code == 401
    payload = response.json()
    assert payload["code"] == "unauthorized"
    assert "Traceback" not in response.text
    assert "sqlalchemy" not in response.text.lower()


def test_missing_and_foreign_records_are_indistinguishable(
    client, register_user, auth_headers, upload_audio, wav_file
):
    owner = register_user()
    analysis = upload_audio(owner, wav_file)
    other = register_user()

    foreign = client.get(f"/api/audio/{analysis['id']}", headers=auth_headers(other))
    missing = client.get("/api/audio/999999", headers=auth_headers(other))
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
