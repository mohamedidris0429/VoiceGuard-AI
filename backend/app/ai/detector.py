"""Real CPU inference for synthetic / spoofed speech detection.

Selected model
--------------
``Vansh180/deepfake-audio-wav2vec2`` (Hugging Face, MIT licence, 94.6 M params,
``Wav2Vec2ForSequenceClassification``, labels ``real`` / ``fake``). It is a
wav2vec 2.0 base checkpoint fine-tuned for binary bonafide-vs-spoof detection on
a balanced subset of ASVspoof 2021 PA. Input: raw mono waveform, 16 kHz.
The published accuracy (92.8%) is self-reported and unverified by an external
benchmark, so results are presented as indicators, never proof.

Everything here is honest by construction:
* no random values, no fallback prediction;
* if the weights cannot be downloaded/loaded, ``ModelUnavailableError`` is raised
  and the caller records the analysis as "unavailable".
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from app.core.config import settings
from app.core.errors import ModelUnavailableError

logger = logging.getLogger("voiceguard.ai")

SPOOF_TOKENS = ("fake", "spoof", "synthetic", "deepfake", "cloned", "generated")
BONAFIDE_TOKENS = ("real", "bonafide", "bona fide", "bona-fide", "genuine", "human", "authentic")

PREDICTION_GENUINE = "genuine"
PREDICTION_SYNTHETIC = "synthetic"

_ERROR_RETRY_COOLDOWN_SECONDS = 120.0


def _sanitize_error(exc: Exception) -> str:
    """Strip filesystem paths and stack noise from an error before it is shown."""
    message = str(exc) or exc.__class__.__name__
    message = re.sub(r"[A-Za-z]:\\[^\s'\"]+", "<path>", message)
    message = re.sub(r"/(?:home|Users|tmp|var)/[^\s'\"]+", "<path>", message)
    message = " ".join(message.split())
    return message[:240]


@dataclass
class Prediction:
    predicted_class: str
    synthetic_probability: float
    confidence: float
    model_id: str
    model_version: str
    labels: dict[str, str]
    windows_analyzed: int
    window_seconds: float
    window_scores: list[float] = field(default_factory=list)
    inference_ms: int = 0
    threshold: float = 0.5
    parameters: int | None = None

    def as_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "labels": self.labels,
            "synthetic_probability": round(self.synthetic_probability, 6),
            "threshold": self.threshold,
            "aggregation": "mean of per-window softmax scores",
            "windows_analyzed": self.windows_analyzed,
            "window_seconds": self.window_seconds,
            "window_scores": [round(score, 6) for score in self.window_scores],
            "inference_ms": self.inference_ms,
            "parameters": self.parameters,
            "device": "cpu",
        }


def _find_synthetic_index(labels: dict[int, str]) -> int | None:
    lowered = {index: name.strip().lower() for index, name in labels.items()}
    for index, name in lowered.items():
        if any(token in name for token in SPOOF_TOKENS):
            return index
    for index, name in lowered.items():
        if any(token in name for token in BONAFIDE_TOKENS):
            # Everything that is not the bonafide class is treated as synthetic.
            others = [i for i in lowered if i != index]
            if len(others) == 1:
                return others[0]
    return None


class VoiceDetector:
    """Lazily loaded, thread-safe singleton around the pretrained classifier."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._model = None
        self._extractor = None
        self._labels: dict[int, str] = {}
        self._synthetic_index: int | None = None
        self._loaded = False
        self._error: str | None = None
        self._error_at = 0.0
        self._model_version = settings.model_id
        self._parameters: int | None = None
        self._load_ms: int | None = None

    # ------------------------------------------------------------------ status
    def status(self, *, probe: bool = False) -> dict:
        if probe and not self._loaded:
            try:
                self._ensure_loaded()
            except ModelUnavailableError:
                pass
        return {
            "available": self._loaded and self._error is None,
            "loaded": self._loaded,
            "model_id": settings.model_id,
            "model_version": self._model_version,
            "device": "cpu",
            "sample_rate": settings.model_sample_rate,
            "labels": {str(k): v for k, v in self._labels.items()},
            "window_seconds": settings.model_window_seconds,
            "max_windows": settings.model_max_windows,
            "threshold": settings.synthetic_threshold,
            "parameters": self._parameters,
            "load_ms": self._load_ms,
            "detail": self._error,
        }

    @property
    def is_loaded(self) -> bool:
        return self._loaded and self._error is None

    # ------------------------------------------------------------------- load
    def _ensure_loaded(self) -> None:
        with self._lock:
            if self._loaded and self._error is None:
                return
            if self._loaded and self._error is not None:
                # Allow a retry after the cooldown (e.g. a transient network failure).
                if time.monotonic() - self._error_at < _ERROR_RETRY_COOLDOWN_SECONDS:
                    raise ModelUnavailableError(
                        f"AI detection is unavailable: {self._error}",
                        code="model_unavailable",
                    )
                self._loaded = False
                self._error = None
            try:
                self._load()
            except ModelUnavailableError:
                raise
            except Exception as exc:  # anything from transformers / torch / disk
                message = _sanitize_error(exc)
                logger.error("Model load failed: %s", message)
                self._loaded = True
                self._error = message
                self._error_at = time.monotonic()
                raise ModelUnavailableError(
                    "AI detection is unavailable: the pretrained model could not be loaded. "
                    "Check network access and the model cache, then retry.",
                    code="model_unavailable",
                ) from exc

    def _load(self) -> None:
        started = time.perf_counter()
        try:
            import torch
            from transformers import AutoConfig, AutoFeatureExtractor, AutoModelForAudioClassification
        except ImportError as exc:  # pragma: no cover - dependencies are installed
            raise ModelUnavailableError(
                "AI detection is unavailable: PyTorch/Transformers are not installed.",
                code="model_unavailable",
            ) from exc

        cache_dir = Path(settings.model_cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("HF_HOME", str(cache_dir))
        # The Xet transfer backend can fail behind restrictive networks; the
        # classic Hub CDN is reliable for this single ~378 MB checkpoint.
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

        threads = settings.model_threads or max(1, min(4, os.cpu_count() or 4))
        torch.set_num_threads(threads)

        load_kwargs = {
            "cache_dir": str(cache_dir),
            "local_files_only": bool(settings.model_offline),
        }

        config = AutoConfig.from_pretrained(settings.model_id, **load_kwargs)
        labels = {int(key): str(value) for key, value in (config.id2label or {}).items()}
        if len(labels) < 2:
            raise RuntimeError("model does not expose a binary class label mapping")

        synthetic_index = _find_synthetic_index(labels)
        if synthetic_index is None:
            raise RuntimeError("model labels do not identify a synthetic/spoof class")

        model = AutoModelForAudioClassification.from_pretrained(settings.model_id, **load_kwargs)
        model.eval()
        for parameter in model.parameters():
            parameter.requires_grad_(False)

        try:
            extractor = AutoFeatureExtractor.from_pretrained(settings.model_id, **load_kwargs)
        except Exception:  # normalisation then falls back to manual standardisation
            extractor = None

        self._model = model
        self._extractor = extractor
        self._labels = labels
        self._synthetic_index = synthetic_index
        self._parameters = int(sum(p.numel() for p in model.parameters()))
        self._model_version = self._resolve_version(config)
        self._load_ms = int((time.perf_counter() - started) * 1000)
        self._loaded = True
        self._error = None
        logger.info(
            "Loaded %s (%s params, labels=%s) in %d ms",
            self._model_version,
            self._parameters,
            labels,
            self._load_ms,
        )

    def _resolve_version(self, config) -> str:
        """Resolve the exact checkpoint revision so results stay reproducible."""
        commit = getattr(config, "_commit_hash", None)
        slug = settings.model_id.replace("/", "--")
        repo_dir = Path(settings.model_cache_dir) / "hub" / f"models--{slug}"

        if not commit:
            ref = repo_dir / "refs" / "main"
            try:
                if ref.exists():
                    commit = ref.read_text(encoding="utf-8").strip() or None
            except OSError:  # pragma: no cover - unreadable cache metadata
                commit = None
        if not commit:
            snapshots = repo_dir / "snapshots"
            try:
                if snapshots.exists():
                    hashes = sorted(entry.name for entry in snapshots.iterdir() if entry.is_dir())
                    commit = hashes[-1] if hashes else None
            except OSError:  # pragma: no cover
                commit = None

        short = commit[:10] if commit else "main"
        return f"{settings.model_id}@{short}"

    # -------------------------------------------------------------- inference
    def _windows(self, waveform: np.ndarray, sample_rate: int) -> list[np.ndarray]:
        window_samples = max(1, int(settings.model_window_seconds * sample_rate))
        total = int(waveform.size)
        if total <= window_samples:
            return [np.pad(waveform, (0, window_samples - total)).astype(np.float32)]

        max_windows = max(1, int(settings.model_max_windows))
        available = total // window_samples
        count = int(min(max_windows, max(1, available)))
        starts = np.linspace(0, total - window_samples, num=count).astype(np.int64)
        return [waveform[start : start + window_samples].astype(np.float32) for start in starts]

    def _to_tensor(self, window: np.ndarray, sample_rate: int):
        import torch

        if self._extractor is not None:
            try:
                batch = self._extractor(
                    window,
                    sampling_rate=sample_rate,
                    return_tensors="pt",
                    return_attention_mask=False,
                )
                return batch["input_values"].to(torch.float32)
            except Exception:  # pragma: no cover - fall back to manual normalisation
                pass
        mean = float(window.mean())
        std = float(window.std()) + 1e-7
        normalised = (window - mean) / std
        return torch.from_numpy(normalised).unsqueeze(0).to(torch.float32)

    def predict(self, waveform: np.ndarray, sample_rate: int) -> Prediction:
        self._ensure_loaded()
        import torch

        if waveform.ndim > 1:
            waveform = waveform.mean(axis=0)
        waveform = np.asarray(waveform, dtype=np.float32).reshape(-1)
        if waveform.size == 0:
            raise ModelUnavailableError("No audio samples were provided for analysis.")
        if not np.isfinite(waveform).all():
            raise ModelUnavailableError("The audio contains invalid samples.")

        windows = self._windows(waveform, sample_rate)
        scores: list[float] = []
        started = time.perf_counter()

        with torch.inference_mode():
            for window in windows:
                tensor = self._to_tensor(window, sample_rate)
                outputs = self._model(input_values=tensor)
                logits = outputs.logits if hasattr(outputs, "logits") else outputs
                probabilities = torch.softmax(logits.float(), dim=-1)[0]
                scores.append(float(probabilities[self._synthetic_index]))

        synthetic_probability = float(np.mean(scores)) if scores else 0.0
        threshold = float(settings.synthetic_threshold)
        predicted = (
            PREDICTION_SYNTHETIC if synthetic_probability >= threshold else PREDICTION_GENUINE
        )
        confidence = (
            synthetic_probability if predicted == PREDICTION_SYNTHETIC else 1.0 - synthetic_probability
        )

        return Prediction(
            predicted_class=predicted,
            synthetic_probability=synthetic_probability,
            confidence=confidence,
            model_id=settings.model_id,
            model_version=self._model_version,
            labels={str(k): v for k, v in self._labels.items()},
            windows_analyzed=len(windows),
            window_seconds=float(settings.model_window_seconds),
            window_scores=scores,
            inference_ms=int((time.perf_counter() - started) * 1000),
            threshold=threshold,
            parameters=self._parameters,
        )


_detector: VoiceDetector | None = None
_detector_lock = threading.Lock()


def get_detector() -> VoiceDetector:
    global _detector
    if _detector is None:
        with _detector_lock:
            if _detector is None:
                _detector = VoiceDetector()
    return _detector
