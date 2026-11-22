"""Phase 2 segment-level analysis tests.

The real model is replaced by a deterministic stub only inside these tests; the
tests still exercise the production service path that calls
``get_detector().predict`` once per supported segment.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from app.ai.detector import Prediction
from app.core.errors import ModelUnavailableError
from app.services import segment_service

SAMPLE_RATE = 16000


def _write_wav(path: Path, seconds: float, *, spoken_seconds: float | None = None) -> Path:
    """Speech-like tone; anything after ``spoken_seconds`` is digital silence."""
    t = np.linspace(0.0, seconds, int(SAMPLE_RATE * seconds), endpoint=False)
    signal = 0.3 * np.sin(2 * np.pi * 150 * t) + 0.1 * np.sin(2 * np.pi * 300 * t)
    if spoken_seconds is not None:
        signal[t >= spoken_seconds] = 0.0
    sf.write(str(path), signal.astype(np.float32), SAMPLE_RATE, subtype="PCM_16")
    return path


def _upload(client, auth_headers, user, path: Path, filename: str | None = None) -> dict:
    with open(path, "rb") as handle:
        files = {"file": (filename or path.name, handle, "audio/wav")}
        response = client.post("/api/audio/upload", files=files, headers=auth_headers(user))
    assert response.status_code == 201, response.text
    return response.json()


def _prediction(score: float) -> Prediction:
    return Prediction(
        predicted_class="synthetic" if score >= 0.5 else "genuine",
        synthetic_probability=score,
        confidence=score if score >= 0.5 else 1.0 - score,
        model_id="test/stub-model",
        model_version="test/stub-model@v1",
        labels={"0": "real", "1": "fake"},
        windows_analyzed=1,
        window_seconds=4.0,
        window_scores=[score],
        inference_ms=1,
        threshold=0.5,
        parameters=100,
    )


class _FakeDetector:
    def __init__(self) -> None:
        self.scores: list[float] = [0.2]
        self.calls = 0
        self.fail_with: Exception | None = None
        self._model_version = "test/stub-model@v1"

    def predict(self, waveform, sample_rate):  # noqa: ANN001
        assert np.asarray(waveform).size > 0
        if self.fail_with is not None:
            raise self.fail_with
        score = self.scores[self.calls % len(self.scores)]
        self.calls += 1
        return _prediction(score)


@pytest.fixture()
def fake_detector(monkeypatch):
    fake = _FakeDetector()
    monkeypatch.setattr(segment_service, "get_detector", lambda: fake)
    return fake


# ------------------------------------------------------------- segment planning


def test_plan_segments_builds_overlapping_windows_that_cover_the_file():
    plans = segment_service.plan_segments(10.0, window=4.0, hop=2.0)

    assert [plan.start_seconds for plan in plans] == [0.0, 2.0, 4.0, 6.0]
    assert plans[-1].end_seconds == pytest.approx(10.0)
    assert all(plan.end_seconds > plan.start_seconds for plan in plans)
    assert plans[1].start_seconds - plans[0].start_seconds == pytest.approx(2.0)
    assert all(plan.state == "done" for plan in plans)


def test_plan_segments_clamps_the_final_segment_and_marks_short_tail_unsupported():
    plans = segment_service.plan_segments(4.5, window=2.0, hop=2.0, min_duration=1.0)

    assert [(p.start_seconds, p.end_seconds) for p in plans] == [
        (0.0, 2.0),
        (2.0, 4.0),
        (4.0, 4.5),
    ]
    assert plans[2].state == "unsupported"
    assert plans[2].reason and "1.00s" in plans[2].reason
    assert plans[2].duration_seconds == pytest.approx(0.5)


def test_plan_segments_treats_audio_shorter_than_the_window_as_one_segment():
    plans = segment_service.plan_segments(1.5, window=4.0, hop=2.0)
    assert len(plans) == 1
    assert (plans[0].start_seconds, plans[0].end_seconds) == (0.0, 1.5)
    assert plans[0].state == "done"


def test_plan_segments_clamps_hop_above_window():
    safe_window, safe_hop = segment_service.clamp_plan(2.0, 9.0)
    assert (safe_window, safe_hop) == (2.0, 2.0)
    plans = segment_service.plan_segments(6.0, window=2.0, hop=9.0)
    assert [p.start_seconds for p in plans] == [0.0, 2.0, 4.0]


# ------------------------------------------------------------------ aggregation


def test_aggregate_weights_scores_by_segment_duration():
    from app.models.analysis import AnalysisSegment

    def _row(index: int, start: float, end: float, score: float) -> AnalysisSegment:
        return AnalysisSegment(
            segment_index=index,
            start_seconds=start,
            end_seconds=end,
            state="done",
            score=score,
        )

    rows = [_row(0, 0.0, 1.0, 0.1), _row(1, 1.0, 4.0, 0.9)]
    aggregate = segment_service.aggregate_segments(rows, 4.0, 0.5)

    # (0.1 * 1s + 0.9 * 3s) / 4s = 0.7
    assert aggregate["score"] == pytest.approx(0.7, abs=1e-6)
    assert aggregate["coverage_seconds"] == pytest.approx(4.0)
    assert aggregate["coverage_ratio"] == 1.0
    assert aggregate["excluded_segments"] == 0
    assert aggregate["whole_file_reliable"] is True
    assert aggregate["method"] == segment_service.AGGREGATION_METHOD


def test_aggregate_excludes_unsupported_and_error_segments():
    from app.models.analysis import AnalysisSegment

    rows = [
        AnalysisSegment(segment_index=0, start_seconds=0.0, end_seconds=2.0, state="done", score=0.9),
        AnalysisSegment(
            segment_index=1, start_seconds=2.0, end_seconds=3.0, state="unsupported", reason="short"
        ),
        AnalysisSegment(
            segment_index=2, start_seconds=3.0, end_seconds=4.0, state="error", reason="failed"
        ),
    ]
    aggregate = segment_service.aggregate_segments(rows, 4.0, 0.5)

    assert aggregate["score"] == pytest.approx(0.9)
    assert aggregate["completed_segments"] == 1
    assert aggregate["excluded_segments"] == 2
    assert aggregate["coverage_seconds"] == pytest.approx(2.0)
    assert aggregate["coverage_ratio"] == pytest.approx(0.5)
    assert aggregate["whole_file_reliable"] is False


# ---------------------------------------------------------------------- access


def test_segments_require_authentication(client):
    assert client.get("/api/forensics/1/segments").status_code == 401
    assert client.post("/api/forensics/1/segments").status_code == 401


def test_segments_reject_other_users_record(
    client, register_user, auth_headers, upload_audio, wav_file
):
    owner = register_user()
    analysis = upload_audio(owner, wav_file)
    other = register_user()

    assert (
        client.get(
            f"/api/forensics/{analysis['id']}/segments", headers=auth_headers(other)
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/forensics/{analysis['id']}/segments", headers=auth_headers(other)
        ).status_code
        == 404
    )


def test_segments_missing_media_returns_gone(
    client, register_user, auth_headers, upload_audio, wav_file, fake_detector
):
    from app.core.config import settings

    user = register_user()
    analysis = upload_audio(user, wav_file)
    for stored in (Path(settings.audio_dir) / str(user["user"]["id"])).glob("*"):
        stored.unlink()

    response = client.post(
        f"/api/forensics/{analysis['id']}/segments", headers=auth_headers(user)
    )
    assert response.status_code == 410


# ---------------------------------------------------------------- computation


def test_segments_not_computed_yet_returns_empty(
    client, register_user, auth_headers, upload_audio, wav_file
):
    user = register_user()
    analysis = upload_audio(user, wav_file)

    response = client.get(
        f"/api/forensics/{analysis['id']}/segments", headers=auth_headers(user)
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["computed"] is False
    assert payload["segments"] == []
    assert payload["aggregate"] is None
    assert payload["caveat"]


def test_segments_persist_scores_for_overlapping_windows(
    client, register_user, auth_headers, upload_audio, wav_file, fake_detector
):
    user = register_user()
    analysis = upload_audio(user, wav_file)
    fake_detector.scores = [0.2, 0.9]

    response = client.post(
        f"/api/forensics/{analysis['id']}/segments?window_seconds=2&hop_seconds=1",
        headers=auth_headers(user),
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["computed"] is True
    assert payload["cached"] is False
    assert payload["total_segments"] == 2
    assert payload["window_seconds"] == 2.0
    assert payload["hop_seconds"] == 1.0
    assert payload["overlap_ratio"] == 0.5
    assert payload["sample_rate"] == SAMPLE_RATE

    first, second = payload["segments"]
    assert (first["start_seconds"], first["end_seconds"]) == (0.0, 2.0)
    assert (second["start_seconds"], second["end_seconds"]) == (1.0, 3.0)
    assert first["duration_seconds"] == 2.0
    assert first["score"] == 0.2 and first["label"] == "genuine"
    assert second["score"] == 0.9 and second["label"] == "synthetic"
    assert first["state"] == "done" and second["state"] == "done"
    assert first["model_version"] == "test/stub-model@v1"

    aggregate = payload["aggregate"]
    # Both windows are 2 s, so the weighted mean equals the plain mean.
    assert aggregate["score"] == pytest.approx(0.55, abs=1e-6)
    assert aggregate["label"] == "synthetic"
    assert aggregate["completed_segments"] == 2
    assert aggregate["excluded_segments"] == 0
    assert aggregate["coverage_ratio"] == 1.0
    assert aggregate["coverage_seconds"] == pytest.approx(3.0, abs=1e-3)
    assert aggregate["whole_file_reliable"] is True

    stored = client.get(
        f"/api/forensics/{analysis['id']}/segments", headers=auth_headers(user)
    )
    assert stored.status_code == 200
    assert stored.json()["total_segments"] == 2
    assert stored.json()["aggregate"]["score"] == pytest.approx(0.55, abs=1e-6)


def test_segments_are_idempotent(
    client, register_user, auth_headers, upload_audio, wav_file, fake_detector
):
    user = register_user()
    analysis = upload_audio(user, wav_file)
    fake_detector.scores = [0.3]
    url = f"/api/forensics/{analysis['id']}/segments?window_seconds=2&hop_seconds=1"

    first = client.post(url, headers=auth_headers(user))
    assert first.status_code == 200, first.text
    calls_after_first = fake_detector.calls

    second = client.post(url, headers=auth_headers(user))
    assert second.status_code == 200, second.text
    assert second.json()["cached"] is True
    assert second.json()["computed_at"] == first.json()["computed_at"]
    assert len(second.json()["segments"]) == len(first.json()["segments"]) == 2
    assert fake_detector.calls == calls_after_first, "cached call must not re-run inference"


def test_segments_force_recomputes_without_duplicates(
    client, register_user, auth_headers, upload_audio, wav_file, fake_detector
):
    user = register_user()
    analysis = upload_audio(user, wav_file)
    fake_detector.scores = [0.1]
    url = f"/api/forensics/{analysis['id']}/segments?window_seconds=2&hop_seconds=1"
    client.post(url, headers=auth_headers(user))

    fake_detector.calls = 0
    fake_detector.scores = [0.95]
    response = client.post(url + "&force=true", headers=auth_headers(user))
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["cached"] is False
    assert payload["total_segments"] == 2
    assert {segment["score"] for segment in payload["segments"]} == {0.95}
    assert payload["aggregate"]["label"] == "synthetic"


def test_segments_mark_silent_windows_unsupported(
    client, register_user, auth_headers, audio_dir, fake_detector
):
    user = register_user()
    path = _write_wav(audio_dir / "half_silent.wav", 4.0, spoken_seconds=2.0)
    analysis = _upload(client, auth_headers, user, path)
    fake_detector.scores = [0.8]

    response = client.post(
        f"/api/forensics/{analysis['id']}/segments?window_seconds=1&hop_seconds=1",
        headers=auth_headers(user),
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["total_segments"] == 4
    assert [segment["state"] for segment in payload["segments"]] == [
        "done",
        "done",
        "unsupported",
        "unsupported",
    ]
    unsupported = [s for s in payload["segments"] if s["state"] != "done"]
    assert all(segment["score"] is None for segment in unsupported)
    assert all(segment["label"] is None for segment in unsupported)
    assert all(segment["reason"] for segment in unsupported)

    aggregate = payload["aggregate"]
    assert aggregate["completed_segments"] == 2
    assert aggregate["unsupported_segments"] == 2
    assert aggregate["excluded_segments"] == 2
    assert aggregate["coverage_ratio"] == pytest.approx(0.5, abs=1e-3)
    assert aggregate["whole_file_reliable"] is False
    assert aggregate["score"] == pytest.approx(0.8, abs=1e-6)
    assert fake_detector.calls == 2, "unsupported windows must not reach the detector"


def test_segments_store_short_tail_as_unsupported(
    client, register_user, auth_headers, audio_dir, fake_detector
):
    user = register_user()
    path = _write_wav(audio_dir / "short_tail.wav", 4.5)
    analysis = _upload(client, auth_headers, user, path)
    fake_detector.scores = [0.6]

    response = client.post(
        f"/api/forensics/{analysis['id']}/segments?window_seconds=2&hop_seconds=2",
        headers=auth_headers(user),
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    states = [segment["state"] for segment in payload["segments"]]
    assert states == ["done", "done", "unsupported"]
    assert payload["segments"][2]["start_seconds"] == 4.0
    assert payload["segments"][2]["end_seconds"] == pytest.approx(4.5)
    assert payload["aggregate"]["coverage_ratio"] == pytest.approx(4.0 / 4.5, abs=1e-3)
    assert payload["aggregate"]["excluded_segments"] == 1
    assert fake_detector.calls == 2


def test_short_recording_is_a_single_window(
    client, register_user, auth_headers, upload_audio, second_wav_file, fake_detector
):
    user = register_user()
    analysis = upload_audio(user, second_wav_file)

    response = client.post(
        f"/api/forensics/{analysis['id']}/segments", headers=auth_headers(user)
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total_segments"] == 1
    assert payload["segments"][0]["start_seconds"] == 0.0
    assert payload["segments"][0]["end_seconds"] == pytest.approx(2.0, abs=1e-2)
    assert payload["overlap_ratio"] == 0.0


def test_segments_model_unavailable_stores_nothing(
    client, register_user, auth_headers, upload_audio, wav_file, fake_detector
):
    user = register_user()
    analysis = upload_audio(user, wav_file)
    fake_detector.fail_with = ModelUnavailableError(
        "AI detection is unavailable: the pretrained model could not be loaded."
    )

    response = client.post(
        f"/api/forensics/{analysis['id']}/segments", headers=auth_headers(user)
    )
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "model_unavailable"

    stored = client.get(
        f"/api/forensics/{analysis['id']}/segments", headers=auth_headers(user)
    ).json()
    assert stored["computed"] is False
    assert stored["segments"] == []


def test_segments_leave_whole_file_result_untouched(
    client, register_user, auth_headers, upload_audio, wav_file, fake_detector
):
    user = register_user()
    analysis = upload_audio(user, wav_file)
    fake_detector.scores = [0.7]
    client.post(
        f"/api/forensics/{analysis['id']}/segments?window_seconds=2&hop_seconds=1",
        headers=auth_headers(user),
    )

    forensics = client.get(
        f"/api/forensics/{analysis['id']}", headers=auth_headers(user)
    ).json()
    assert forensics["model"]["status"] == "pending"
    assert forensics["model"]["model_score"] is None


# ---------------------------------------------------------------- validation


@pytest.mark.parametrize(
    "query",
    ["window_seconds=0", "window_seconds=45", "hop_seconds=0", "hop_seconds=45"],
)
def test_segments_reject_invalid_plan_parameters(
    client, register_user, auth_headers, upload_audio, wav_file, query
):
    user = register_user()
    analysis = upload_audio(user, wav_file)
    response = client.post(
        f"/api/forensics/{analysis['id']}/segments?{query}", headers=auth_headers(user)
    )
    assert response.status_code == 422, response.text


def test_segments_enforce_the_segment_count_limit(
    client, register_user, auth_headers, audio_dir
):
    user = register_user()
    path = _write_wav(audio_dir / "ten_seconds.wav", 10.0)
    analysis = _upload(client, auth_headers, user, path)

    response = client.post(
        f"/api/forensics/{analysis['id']}/segments?window_seconds=0.5&hop_seconds=0.1",
        headers=auth_headers(user),
    )
    assert response.status_code == 422, response.text
    assert "segments" in response.json()["detail"].lower()


# ------------------------------------------- partial vs whole-file aggregation


def test_partial_coverage_never_exposes_a_whole_file_label(
    client, register_user, auth_headers, audio_dir, fake_detector
):
    """Half the file is silent: scores stay diagnostic, the verdict does not exist."""
    user = register_user()
    path = _write_wav(audio_dir / "half_silent_scope.wav", 4.0, spoken_seconds=2.0)
    analysis = _upload(client, auth_headers, user, path)
    fake_detector.scores = [0.8]

    payload = client.post(
        f"/api/forensics/{analysis['id']}/segments?window_seconds=1&hop_seconds=1",
        headers=auth_headers(user),
    ).json()

    aggregate = payload["aggregate"]
    assert aggregate["whole_file_reliable"] is False
    assert aggregate["scope"] == "partial"
    assert aggregate["label"] is None, "partial results must not carry a whole-file verdict"
    assert aggregate["scored_label"] == "synthetic", "diagnostic label of scored segments is kept"
    assert aggregate["score"] == pytest.approx(0.8, abs=1e-6)
    assert aggregate["coverage_ratio"] == pytest.approx(0.5, abs=1e-3)
    assert aggregate["excluded_segments"] == 2
    assert "50.0%" in aggregate["reliability_note"]
    assert "2 segment(s) were excluded" in aggregate["reliability_note"]

    # Segment-level results are untouched by the scoping decision.
    scored = [s for s in payload["segments"] if s["state"] == "done"]
    assert [s["score"] for s in scored] == [0.8, 0.8]
    assert [s["label"] for s in scored] == ["synthetic", "synthetic"]


def test_partial_tail_is_scoped_as_partial(
    client, register_user, auth_headers, audio_dir, fake_detector
):
    user = register_user()
    path = _write_wav(audio_dir / "short_tail_scope.wav", 4.5)
    analysis = _upload(client, auth_headers, user, path)
    fake_detector.scores = [0.9]

    payload = client.post(
        f"/api/forensics/{analysis['id']}/segments?window_seconds=2&hop_seconds=2",
        headers=auth_headers(user),
    ).json()

    aggregate = payload["aggregate"]
    assert aggregate["whole_file_reliable"] is False
    assert aggregate["scope"] == "partial"
    assert aggregate["label"] is None
    assert aggregate["scored_label"] == "synthetic"
    assert aggregate["coverage_ratio"] == pytest.approx(4.0 / 4.5, abs=1e-3)
    assert "1 segment(s) were excluded" in aggregate["reliability_note"]


def test_reliable_coverage_carries_the_whole_file_label(
    client, register_user, auth_headers, upload_audio, wav_file, fake_detector
):
    user = register_user()
    analysis = upload_audio(user, wav_file)
    fake_detector.scores = [0.2, 0.9]

    aggregate = client.post(
        f"/api/forensics/{analysis['id']}/segments?window_seconds=2&hop_seconds=1",
        headers=auth_headers(user),
    ).json()["aggregate"]

    assert aggregate["whole_file_reliable"] is True
    assert aggregate["scope"] == "whole_file"
    assert aggregate["label"] == "synthetic"
    assert aggregate["scored_label"] == aggregate["label"]
    assert aggregate["reliability_note"] is None
    assert aggregate["coverage_ratio"] == 1.0


def test_aggregate_without_any_score_has_no_verdict():
    from app.models.analysis import AnalysisSegment

    rows = [
        AnalysisSegment(
            segment_index=0, start_seconds=0.0, end_seconds=1.0, state="unsupported", reason="silent"
        ),
        AnalysisSegment(
            segment_index=1, start_seconds=1.0, end_seconds=2.0, state="error", reason="failed"
        ),
    ]
    aggregate = segment_service.aggregate_segments(rows, 2.0, 0.5)

    assert aggregate["score"] is None
    assert aggregate["label"] is None
    assert aggregate["scored_label"] is None
    assert aggregate["scope"] == "partial"
    assert aggregate["whole_file_reliable"] is False
    assert aggregate["coverage_ratio"] == 0.0
    assert "no aggregate verdict" in aggregate["reliability_note"].lower()


def test_aggregate_response_contract(
    client, register_user, auth_headers, upload_audio, wav_file, fake_detector
):
    """Contract: a label exists only when the aggregate is reliable."""
    user = register_user()
    reliable_analysis = upload_audio(user, wav_file)
    reliable = client.post(
        f"/api/forensics/{reliable_analysis['id']}/segments?window_seconds=2&hop_seconds=1",
        headers=auth_headers(user),
    ).json()["aggregate"]

    required = {
        "method",
        "score",
        "label",
        "scored_label",
        "scope",
        "reliability_note",
        "threshold",
        "completed_segments",
        "unsupported_segments",
        "error_segments",
        "excluded_segments",
        "coverage_seconds",
        "coverage_ratio",
        "whole_file_reliable",
        "whole_file_score",
    }
    assert required <= set(reliable)
    assert reliable["scope"] in {"partial", "whole_file"}
    assert reliable["completed_segments"] + reliable["excluded_segments"] == 2
    for key in ("completed_segments", "excluded_segments"):
        assert isinstance(reliable[key], int)
    assert 0.0 <= reliable["coverage_ratio"] <= 1.0

    # The invariant also holds for a partial result from the same aggregation.
    from app.models.analysis import AnalysisSegment

    partial_rows = [
        AnalysisSegment(segment_index=0, start_seconds=0.0, end_seconds=1.0, state="done", score=0.9),
        AnalysisSegment(
            segment_index=1, start_seconds=1.0, end_seconds=9.0, state="unsupported", reason="silent"
        ),
    ]
    partial = segment_service.aggregate_segments(partial_rows, 9.0, 0.5)
    assert partial["whole_file_reliable"] is False
    assert partial["scope"] == "partial"
    assert partial["label"] is None and partial["scored_label"] == "synthetic"
    assert partial["coverage_ratio"] == pytest.approx(1 / 9, abs=1e-3)
