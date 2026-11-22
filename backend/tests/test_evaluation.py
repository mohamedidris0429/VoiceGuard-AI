"""Phase 5 - metric math and the evaluation runner (no dataset is shipped)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from app.ai.detector import Prediction
from app.services import evaluation_service
from scripts import evaluate_model

SAMPLE_RATE = 16000


def _wav(path: Path, seconds: float = 1.2, amplitude: float = 0.3) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    t = np.linspace(0.0, seconds, int(SAMPLE_RATE * seconds), endpoint=False)
    sf.write(str(path), (amplitude * np.sin(2 * np.pi * 160 * t)).astype(np.float32), SAMPLE_RATE)
    return path


class _ScriptedDetector:
    """Returns fixed scores in file order so metric math can be asserted."""

    def __init__(self, scores: list[float]):
        self._scores = list(scores)
        self.seen: list[int] = []

    def predict(self, waveform, sample_rate):  # noqa: ANN001
        self.seen.append(int(waveform.size))
        score = self._scores.pop(0)
        predicted = "synthetic" if score >= 0.5 else "genuine"
        return Prediction(
            predicted_class=predicted,
            synthetic_probability=score,
            confidence=score if predicted == "synthetic" else 1 - score,
            model_id="test/scripted",
            model_version="test/scripted@v1",
            labels={"0": "real", "1": "fake"},
            windows_analyzed=1,
            window_seconds=4.0,
            window_scores=[score],
            inference_ms=1,
            threshold=0.5,
            parameters=10,
        )


# --------------------------------------------------------------- metric math


def test_perfect_separation_metrics():
    metrics = evaluation_service.evaluate_scores([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9])

    assert metrics["accuracy"] == 1.0
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
    assert metrics["f1"] == 1.0
    assert metrics["specificity"] == 1.0
    assert metrics["roc_auc"] == 1.0
    assert metrics["confusion_matrix"] == {"tp": 2, "fp": 0, "tn": 2, "fn": 0}


def test_threshold_confusion_and_partial_metrics():
    metrics = evaluation_service.evaluate_scores([1, 1, 0, 0], [0.6, 0.4, 0.7, 0.2])

    assert metrics["confusion_matrix"] == {"tp": 1, "fp": 1, "tn": 1, "fn": 1}
    assert metrics["accuracy"] == 0.5
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 0.5
    assert metrics["f1"] == 0.5


def test_threshold_is_respected():
    low = evaluation_service.evaluate_scores([0, 1], [0.4, 0.45], threshold=0.3)
    high = evaluation_service.evaluate_scores([0, 1], [0.4, 0.45], threshold=0.9)

    assert low["confusion_matrix"]["tp"] == 1
    assert high["confusion_matrix"]["tp"] == 0
    assert high["confusion_matrix"]["fn"] == 1


def test_roc_auc_handles_ties_and_single_class():
    assert evaluation_service.roc_auc([0, 1], [0.5, 0.5]) == 0.5
    assert evaluation_service.evaluate_scores([0, 0], [0.1, 0.2])["roc_auc"] is None
    assert evaluation_service.evaluate_scores([1, 1, 0], [0.1, 0.4, 0.9])["roc_auc"] == 0.0


def test_metric_input_is_validated():
    with pytest.raises(ValueError):
        evaluation_service.evaluate_scores([0, 1], [0.1])
    with pytest.raises(ValueError):
        evaluation_service.evaluate_scores([], [])


# ------------------------------------------------------------------- dataset


def test_discover_dataset_requires_labelled_directories(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        evaluation_service.discover_dataset(tmp_path / "missing")

    (tmp_path / "unlabelled").mkdir()
    _wav(tmp_path / "unlabelled" / "a.wav")
    with pytest.raises(ValueError, match="No labelled audio"):
        evaluation_service.discover_dataset(tmp_path)


def test_evaluate_directory_runs_detector_and_records_errors(tmp_path):
    for index in range(2):
        _wav(tmp_path / "spoof" / f"spoof-{index}.wav")
        _wav(tmp_path / "bonafide" / f"real-{index}.wav")
    corrupt = tmp_path / "spoof" / "broken.wav"
    corrupt.write_bytes(b"RIFF____WAVE" + b"junk" * 30)

    # Discovery is alphabetical, so bonafide samples are scored first.
    detector = _ScriptedDetector([0.2, 0.1, 0.9, 0.8])
    result = evaluation_service.evaluate_directory(
        tmp_path, detector=detector, limit_per_class=None
    )

    # Order is sorted: bonafide first, then spoof (including the corrupt file).
    assert len(result.samples) == 4
    assert len(result.errors) == 1
    assert "broken.wav" in result.errors[0]["file"]
    assert result.model_version == "test/scripted@v1"

    data = result.to_dict()
    metrics = data["metrics"]
    assert metrics["accuracy"] == 1.0
    assert metrics["roc_auc"] == 1.0
    assert data["sample_count"] == 4
    assert data["error_count"] == 1
    assert "not a claim of accuracy" in data["disclaimer"]


def test_limit_per_class_and_report_files(tmp_path):
    for index in range(3):
        _wav(tmp_path / "synthetic" / f"syn-{index}.wav")
        _wav(tmp_path / "genuine" / f"gen-{index}.wav")

    detector = _ScriptedDetector([0.1, 0.2, 0.85, 0.95])
    result = evaluation_service.evaluate_directory(
        tmp_path, detector=detector, limit_per_class=2
    )
    assert len(result.samples) == 4

    json_path, markdown_path = evaluation_service.write_report(result, tmp_path / "out" / "eval")
    assert json_path.exists() and json_path.suffix == ".json"
    assert markdown_path.exists() and markdown_path.suffix == ".md"

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["metrics"]["confusion_matrix"]["tp"] == 2
    assert payload["samples"][0]["label"] in {0, 1}
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "ROC-AUC" in markdown
    assert "Confusion matrix" in markdown


def test_cli_refuses_missing_dataset(tmp_path, capsys):
    code = evaluate_model.main(
        ["--dataset", str(tmp_path / "nope"), "--output", str(tmp_path / "report"), "--quiet"]
    )
    assert code == 2
    assert "does not exist" in capsys.readouterr().err
    assert not (tmp_path / "report.json").exists()
