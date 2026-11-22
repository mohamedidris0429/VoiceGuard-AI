"""Phase 5 - evaluation metrics and a reproducible dataset runner.

No dataset ships with the project, so this module **computes** metrics from a
directory the operator supplies; it never invents them. The detector is always
the real pretrained model unless a caller injects one for tests.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np

AUDIO_EXTENSIONS = {".wav", ".mp3"}
POSITIVE_DIRS = ("spoof", "fake", "synthetic", "cloned")
NEGATIVE_DIRS = ("bonafide", "bona-fide", "genuine", "real", "human")


@dataclass
class DatasetFile:
    path: Path
    label: int  # 1 = spoof/synthetic, 0 = bonafide


@dataclass
class EvaluationResult:
    samples: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    threshold: float = 0.5
    model_version: str | None = None
    dataset_root: str = ""

    def to_dict(self) -> dict[str, Any]:
        labels = [row["label"] for row in self.samples]
        scores = [row["score"] for row in self.samples]
        metrics = (
            evaluate_scores(labels, scores, threshold=self.threshold)
            if labels
            else None
        )
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dataset_root": self.dataset_root,
            "model_version": self.model_version,
            "threshold": self.threshold,
            "sample_count": len(self.samples),
            "error_count": len(self.errors),
            "metrics": metrics,
            "samples": self.samples,
            "errors": self.errors,
            "disclaimer": (
                "Metrics describe the supplied dataset and this checkpoint only. "
                "They are not a claim of accuracy on other audio, speakers, languages "
                "or codecs, and they do not establish that a single recording is cloned."
            ),
        }

    def to_markdown(self) -> str:
        data = self.to_dict()
        metrics = data["metrics"]
        lines = [
            "# VoiceGuard AI - detector evaluation",
            "",
            f"- Generated: {data['generated_at']}",
            f"- Dataset: `{data['dataset_root']}`",
            f"- Model: `{data['model_version'] or 'unknown'}`",
            f"- Threshold: {data['threshold']}",
            f"- Samples: {data['sample_count']} ({data['error_count']} unreadable)",
            "",
        ]
        if not metrics:
            lines += ["**No readable samples were evaluated, so there are no metrics.**", ""]
        else:
            matrix = metrics["confusion_matrix"]
            lines += [
                "## Metrics",
                "",
                "| metric | value |",
                "| --- | --- |",
                f"| accuracy | {metrics['accuracy']:.4f} |",
                f"| precision (spoof) | {metrics['precision']:.4f} |",
                f"| recall (spoof) | {metrics['recall']:.4f} |",
                f"| F1 (spoof) | {metrics['f1']:.4f} |",
                f"| specificity (bonafide) | {metrics['specificity']:.4f} |",
                f"| ROC-AUC | {metrics['roc_auc'] if metrics['roc_auc'] is not None else 'n/a (one class)'} |",
                "",
                "## Confusion matrix",
                "",
                "| | predicted spoof | predicted bonafide |",
                "| --- | --- | --- |",
                f"| actual spoof | {matrix['tp']} | {matrix['fn']} |",
                f"| actual bonafide | {matrix['fp']} | {matrix['tn']} |",
                "",
                f"**False positives:** {matrix['fp']} · **False negatives:** {matrix['fn']}",
                "",
            ]
        lines += [f"> {data['disclaimer']}", ""]
        return "\n".join(lines)


def discover_dataset(root: Path) -> list[DatasetFile]:
    """Find audio under labelled subdirectories. Raises when nothing is labelled."""
    root = Path(root)
    if not root.is_dir():
        raise ValueError(f"Dataset directory does not exist: {root}")

    files: list[DatasetFile] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        name = child.name.lower()
        if name in POSITIVE_DIRS:
            label = 1
        elif name in NEGATIVE_DIRS:
            label = 0
        else:
            continue
        for path in sorted(child.rglob("*")):
            if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS:
                files.append(DatasetFile(path=path, label=label))

    if not files:
        raise ValueError(
            "No labelled audio found. Expected sub-directories named one of "
            f"{POSITIVE_DIRS} and one of {NEGATIVE_DIRS}, each containing .wav/.mp3 files."
        )
    return files


def evaluate_scores(
    labels: list[int], scores: list[float], *, threshold: float = 0.5
) -> dict[str, Any]:
    """Binary metrics for spoof-positive predictions at a fixed threshold."""
    if len(labels) != len(scores):
        raise ValueError("labels and scores must have the same length")
    if not labels:
        raise ValueError("at least one sample is required")

    labels_array = np.asarray(labels, dtype=np.int64)
    score_array = np.asarray(scores, dtype=np.float64)
    predicted = (score_array >= float(threshold)).astype(np.int64)

    tp = int(np.sum((predicted == 1) & (labels_array == 1)))
    fp = int(np.sum((predicted == 1) & (labels_array == 0)))
    tn = int(np.sum((predicted == 0) & (labels_array == 0)))
    fn = int(np.sum((predicted == 0) & (labels_array == 1)))

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    accuracy = (tp + tn) / len(labels_array)
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    return {
        "threshold": float(threshold),
        "accuracy": round(float(accuracy), 6),
        "precision": round(float(precision), 6),
        "recall": round(float(recall), 6),
        "f1": round(float(f1), 6),
        "specificity": round(float(specificity), 6),
        "roc_auc": roc_auc(labels, scores),
        "confusion_matrix": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "support": {
            "spoof": int(np.sum(labels_array == 1)),
            "bonafide": int(np.sum(labels_array == 0)),
        },
    }


def roc_auc(labels: list[int], scores: list[float]) -> float | None:
    """Rank-based ROC-AUC with average ranks for ties (Mann-Whitney U)."""
    labels_array = np.asarray(labels, dtype=np.int64)
    score_array = np.asarray(scores, dtype=np.float64)
    positives = int(np.sum(labels_array == 1))
    negatives = int(np.sum(labels_array == 0))
    if positives == 0 or negatives == 0:
        return None

    ranks = _average_ranks(score_array)
    rank_sum = float(np.sum(ranks[labels_array == 1]))
    auc = (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)
    return round(float(auc), 6)


def _average_ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    sorted_values = values[order]
    ranks = np.empty(values.size, dtype=np.float64)
    index = 0
    while index < values.size:
        end = index + 1
        while end < values.size and sorted_values[end] == sorted_values[index]:
            end += 1
        average = (index + end + 1) / 2.0  # 1-based ranks index+1 .. end
        ranks[order[index:end]] = average
        index = end
    return ranks


def evaluate_directory(
    root: Path,
    *,
    threshold: float = 0.5,
    limit_per_class: int | None = None,
    detector: Callable | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> EvaluationResult:
    """Run the real detector over a labelled directory, one file at a time."""
    from app.core.config import settings
    from app.services import audio_service

    files = discover_dataset(Path(root))
    if limit_per_class:
        kept: list[DatasetFile] = []
        counts = {0: 0, 1: 0}
        for item in files:
            if counts[item.label] < limit_per_class:
                kept.append(item)
                counts[item.label] += 1
        files = kept

    if detector is None:
        from app.ai.detector import get_detector

        detector = get_detector()

    result = EvaluationResult(threshold=threshold, dataset_root=str(Path(root)))
    total = len(files)
    for position, item in enumerate(files, start=1):
        started = time.perf_counter()
        try:
            waveform, sample_rate = audio_service.load_model_input(
                item.path, settings.model_sample_rate
            )
            prediction = detector.predict(waveform, sample_rate)
        except Exception as exc:  # unreadable / unavailable: recorded, never scored
            result.errors.append({"file": str(item.path), "error": str(exc)[:200]})
            if progress:
                progress(position, total)
            continue

        result.samples.append(
            {
                "file": str(item.path),
                "label": item.label,
                "score": round(float(prediction.synthetic_probability), 6),
                "predicted": prediction.predicted_class,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
            }
        )
        result.model_version = prediction.model_version
        if progress:
            progress(position, total)

    return result


def write_report(result: EvaluationResult, output: Path) -> tuple[Path, Path]:
    """Write the JSON and Markdown artefacts next to each other."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    json_path = output.with_suffix(".json")
    markdown_path = output.with_suffix(".md")
    json_path.write_text(
        json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    markdown_path.write_text(result.to_markdown(), encoding="utf-8")
    return json_path, markdown_path
