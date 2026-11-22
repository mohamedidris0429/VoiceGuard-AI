"""History, analytics, report and ownership tests."""

from __future__ import annotations

import uuid


def _upload_and_analyze(client, user, headers, path, filename):
    with open(path, "rb") as handle:
        upload = client.post(
            "/api/audio/upload",
            files={"file": (filename, handle, "audio/wav")},
            headers=headers(user),
        )
    assert upload.status_code == 201, upload.text
    analysis_id = upload.json()["id"]
    analyzed = client.post(
        "/api/audio/analyze", json={"analysis_id": analysis_id}, headers=headers(user)
    )
    assert analyzed.status_code == 200, analyzed.text
    return analyzed.json()


# --------------------------------------------------------------------- history
def test_history_empty_state(client, register_user, auth_headers):
    user = register_user()
    response = client.get("/api/history", headers=auth_headers(user))
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["pages"] == 1


def test_history_pagination_and_search(
    client, register_user, auth_headers, wav_file, second_wav_file, stub_detector
):
    user = register_user()
    for index in range(3):
        _upload_and_analyze(client, user, auth_headers, wav_file, f"interview-{index}.wav")
    _upload_and_analyze(client, user, auth_headers, second_wav_file, "voicemail.wav")

    page1 = client.get(
        "/api/history", params={"page": 1, "page_size": 2}, headers=auth_headers(user)
    ).json()
    assert page1["total"] == 4
    assert page1["pages"] == 2
    assert len(page1["items"]) == 2

    page2 = client.get(
        "/api/history", params={"page": 2, "page_size": 2}, headers=auth_headers(user)
    ).json()
    ids_page1 = {item["id"] for item in page1["items"]}
    ids_page2 = {item["id"] for item in page2["items"]}
    assert ids_page1.isdisjoint(ids_page2)

    search = client.get(
        "/api/history", params={"q": "voicemail"}, headers=auth_headers(user)
    ).json()
    assert search["total"] == 1
    assert search["items"][0]["filename"] == "voicemail.wav"


def test_history_filters_and_sorting(
    client, register_user, auth_headers, wav_file, stub_detector
):
    user = register_user()
    _upload_and_analyze(client, user, auth_headers, wav_file, "b-file.wav")
    _upload_and_analyze(client, user, auth_headers, wav_file, "a-file.wav")

    ascending = client.get(
        "/api/history",
        params={"sort": "filename", "order": "asc"},
        headers=auth_headers(user),
    ).json()
    assert [item["filename"] for item in ascending["items"]] == ["a-file.wav", "b-file.wav"]

    genuine_only = client.get(
        "/api/history", params={"prediction": "genuine"}, headers=auth_headers(user)
    ).json()
    assert genuine_only["total"] == 2

    synthetic_only = client.get(
        "/api/history", params={"prediction": "synthetic"}, headers=auth_headers(user)
    ).json()
    assert synthetic_only["total"] == 0

    bad_filter = client.get(
        "/api/history", params={"status": "nonsense"}, headers=auth_headers(user)
    )
    assert bad_filter.status_code == 422


def test_history_detail(client, register_user, auth_headers, wav_file, stub_detector):
    user = register_user()
    analysis = _upload_and_analyze(client, user, auth_headers, wav_file, "detail.wav")
    response = client.get(f"/api/history/{analysis['id']}", headers=auth_headers(user))
    assert response.status_code == 200
    assert response.json()["id"] == analysis["id"]


# ------------------------------------------------------------------- analytics
def test_analytics_summary_and_trends(
    client, register_user, auth_headers, wav_file, second_wav_file, stub_detector
):
    user = register_user()
    _upload_and_analyze(client, user, auth_headers, wav_file, "one.wav")
    _upload_and_analyze(client, user, auth_headers, second_wav_file, "two.wav")

    summary = client.get("/api/analytics/summary", headers=auth_headers(user)).json()
    assert summary["total_analyses"] == 2
    assert summary["genuine"] == 2
    assert summary["synthetic"] == 0
    assert summary["average_duration"] is not None
    assert summary["last_successful_at"] is not None

    trends = client.get(
        "/api/analytics/trends", params={"days": 7}, headers=auth_headers(user)
    ).json()
    assert trends["range_days"] == 7
    assert len(trends["daily"]) == 7
    assert sum(point["total"] for point in trends["daily"]) == 2
    assert len(trends["confidence_buckets"]) == 5
    assert sum(bucket["count"] for bucket in trends["confidence_buckets"]) == 2
    assert len(trends["duration_buckets"]) == 5


def test_analytics_are_user_scoped(client, register_user, auth_headers, wav_file, stub_detector):
    first = register_user()
    second = register_user()
    _upload_and_analyze(client, first, auth_headers, wav_file, "mine.wav")

    summary = client.get("/api/analytics/summary", headers=auth_headers(second)).json()
    assert summary["total_analyses"] == 0
    assert summary["last_successful_at"] is None


# --------------------------------------------------------------------- reports
def test_report_download_is_a_real_pdf(
    client, register_user, auth_headers, wav_file, stub_detector
):
    user = register_user()
    analysis = _upload_and_analyze(client, user, auth_headers, wav_file, "report.wav")

    response = client.get(f"/api/reports/{analysis['id']}/download", headers=auth_headers(user))
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")
    assert len(response.content) > 2000


def test_report_metadata_persists_reference(
    client, register_user, auth_headers, wav_file, stub_detector
):
    user = register_user()
    analysis = _upload_and_analyze(client, user, auth_headers, wav_file, "meta.wav")

    first = client.get(f"/api/reports/{analysis['id']}/metadata", headers=auth_headers(user)).json()
    second = client.get(f"/api/reports/{analysis['id']}/metadata", headers=auth_headers(user)).json()
    assert first["report_reference"].startswith("VG-")
    assert first["report_reference"] == second["report_reference"]


def test_report_requires_completed_analysis(client, register_user, auth_headers, wav_file):
    user = register_user()
    with open(wav_file, "rb") as handle:
        upload = client.post(
            "/api/audio/upload",
            files={"file": ("pending.wav", handle, "audio/wav")},
            headers=auth_headers(user),
        )
    analysis_id = upload.json()["id"]
    response = client.get(f"/api/reports/{analysis_id}/download", headers=auth_headers(user))
    assert response.status_code == 409


# ------------------------------------------------------------------- ownership
def test_users_cannot_access_other_users_records(
    client, register_user, auth_headers, wav_file, stub_detector
):
    owner = register_user()
    intruder = register_user()
    analysis = _upload_and_analyze(client, owner, auth_headers, wav_file, "private.wav")
    analysis_id = analysis["id"]

    for path in (
        f"/api/audio/{analysis_id}",
        f"/api/audio/{analysis_id}/waveform",
        f"/api/audio/{analysis_id}/spectrogram",
        f"/api/history/{analysis_id}",
        f"/api/reports/{analysis_id}/download",
        f"/api/reports/{analysis_id}/metadata",
    ):
        response = client.get(path, headers=auth_headers(intruder))
        assert response.status_code == 404, f"{path} leaked another user's record"

    delete = client.delete(f"/api/audio/{analysis_id}", headers=auth_headers(intruder))
    assert delete.status_code == 404

    analyze = client.post(
        "/api/audio/analyze",
        json={"analysis_id": analysis_id},
        headers=auth_headers(intruder),
    )
    assert analyze.status_code == 404

    still_there = client.get(f"/api/audio/{analysis_id}", headers=auth_headers(owner))
    assert still_there.status_code == 200


def test_health_and_model_status(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    body = health.json()
    assert body["database"] == "connected"
    assert body["status"] in {"operational", "degraded"}

    model = client.get("/api/model/status")
    assert model.status_code == 200
    assert model.json()["device"] == "cpu"
    assert model.json()["sample_rate"] == 16000


def test_comparison_endpoint(
    client, register_user, auth_headers, wav_file, second_wav_file, stub_detector
):
    user = register_user()
    with open(wav_file, "rb") as left, open(second_wav_file, "rb") as right:
        response = client.post(
            "/api/audio/compare",
            files={
                "file_a": ("a.wav", left, "audio/wav"),
                "file_b": ("b.wav", right, "audio/wav"),
            },
            headers=auth_headers(user),
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["left"]["analysis_status"] == "completed"
    assert body["right"]["analysis_status"] == "completed"
    assert body["left"]["audio_duration"] > body["right"]["audio_duration"]
    assert body["duration_delta_seconds"] == round(
        body["left"]["audio_duration"] - body["right"]["audio_duration"], 3
    )
    assert "not conclusive" in body["disclaimer"].lower()
    assert body["left"]["filename"] != body["right"]["filename"]


def test_comparison_requires_two_files(client, register_user, auth_headers, wav_file):
    user = register_user()
    with open(wav_file, "rb") as handle:
        response = client.post(
            "/api/audio/compare",
            files={"file_a": ("a.wav", handle, "audio/wav")},
            headers=auth_headers(user),
        )
    assert response.status_code == 422
