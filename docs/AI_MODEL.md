# AI model documentation

## 1. Selection

| Field | Value |
| --- | --- |
| Model ID | `Vansh180/deepfake-audio-wav2vec2` |
| Source | https://huggingface.co/Vansh180/deepfake-audio-wav2vec2 |
| Licence | MIT (declared in the model card metadata) |
| Architecture | `Wav2Vec2ForSequenceClassification` — wav2vec 2.0 base encoder (12 transformer layers, 768 hidden) + mean-pool + linear classifier |
| Parameters | 94,569,090 float32 (~378 MB) |
| Labels | `0 = real`, `1 = fake` |
| Input format | Raw mono waveform, 16,000 Hz, float32 (variable length, padded/truncated to whole windows) |
| Reported results | 92.8% accuracy, 89.7% precision, 88.0% recall, F1 92.4% — **self-reported, marked unverified** by the author |
| Training data | Balanced subset of ASVspoof 2021 PA (physical-access / replay-spoof scenario) |
| Runtime | CPU (PyTorch CPU wheel). No CUDA, no quantization, no GPU needed. |

Requirements it satisfies: lightweight enough for CPU inference on a low-RAM laptop, a pretrained
checkpoint specifically intended for bonafide-vs-spoof speech classification, a permissive licence, and a
standard Transformers layout (`config.json`, `preprocessor_config.json`, `model.safetensors`) that needs no
custom architecture code.

Rejected alternatives and why:

- `lab260/*` and `SpeechAntiSpoofingBenchmarks/W2V2-AASIST` — stronger published EERs, but 300 M+
  parameters and/or custom network definitions, which is too heavy for a 4 GB CPU-only target.
- `caa-speech-detection-asvspoof2019/wav2vec2` — good EER, but the checkpoint is a custom `best.pt`
  state dict with bespoke head code and a 362 MB download; higher integration risk.
- Generic audio classifiers (AudioSet, speech commands, emotion) — these do not detect spoofing and were
  ruled out on correctness grounds.

## 2. Preprocessing (`app/services/audio_service.py`, `app/ai/detector.py`)

1. Container is validated first (RIFF/WAVE header, ID3 or MPEG frame sync), then parsed with libsndfile.
2. Duration must be 1–60 s, sample rate ≥ 8 kHz, 1–8 channels.
3. `librosa.load(..., sr=16000, mono=True)` — channels are averaged, audio resampled to the model rate.
4. Silent recordings (peak < 1e-4) are rejected rather than scored.
5. Leading/trailing near-silence is trimmed (`top_db=40`), keeping ≥ 0.5 s.
6. Up to `MODEL_MAX_WINDOWS` (3) evenly spaced windows of `MODEL_WINDOW_SECONDS` (4 s) are taken; clips
   shorter than one window are zero-padded.
7. Each window is normalised with the model's `AutoFeatureExtractor` (falling back to zero-mean/unit-variance).

## 3. Scoring

```
per_window[i] = softmax(logits_i)[synthetic_index]
synthetic_probability = mean(per_window)
predicted_class = "synthetic" if synthetic_probability >= 0.5 else "genuine"
confidence = synthetic_probability            (when synthetic)
           = 1 - synthetic_probability        (when genuine)
```

`model_details` stored with each analysis contains: model id, labels, per-window scores, window count and
length, aggregation method, threshold, inference time, parameter count and device. `model_version` is the
model id with the resolved 10-character commit hash, e.g. `Vansh180/deepfake-audio-wav2vec2@e1197e2063`.

The index of the synthetic class is discovered from `config.id2label` (`fake`/`spoof`/`synthetic`/
`deepfake`/`cloned`/`generated`, falling back to "the class that is not bonafide"). If no such mapping
exists, loading fails loudly — the app never guesses which logit means "fake".

## 4. Failure handling

| Condition | Behaviour |
| --- | --- |
| Weights missing and no network | `ModelUnavailableError`; analysis row stored as `unavailable` with a sanitised reason; HTTP 200 with that state (not a fake prediction) |
| Model loaded but audio silent/undecodable | `failed` with a safe validation message |
| Unexpected inference exception | `failed`, generic message to the client, full traceback logged server-side |
| Model retry | After a failed load, a retry is allowed after a 120 s cooldown |

`GET /api/model/status?load=true` forces a load attempt and reports the sanitised error, so operators can
diagnose without reading the client-facing message.

## 5. Evaluation notes

The model card reports 92.8% accuracy on a balanced ASVspoof 2021 PA subset. This project **did not
independently re-evaluate** the checkpoint on a held-out benchmark, and does not claim those numbers as its
own. What was verified here:

- The architecture, labels and input rate load correctly with the installed Transformers/PyTorch versions.
- Real inference executes on CPU and produces probabilities in [0, 1] with a recorded model revision.
- The pipeline handles WAV and MP3 inputs, mono/stereo, resampling and windowing.

For a formal evaluation, follow the ASVspoof 2019/2021 protocols (EER, tandem min-t-DCF) and the WaveFake
protocol for vocoder-generated speech. Respect each dataset's licence and access conditions; none are
bundled with this repository.

## 6. Known weaknesses

- Trained on replay/physical-access spoofing, so cutting-edge neural TTS or voice conversion may be missed.
- Accurate synthetic probability does not imply calibrated probability; the 0.5 threshold is a sensible
  default, not a validated operating point.
- Compression, denoising, music beds and multiple speakers all degrade reliability.
- The model says nothing about *who* is speaking. Speaker verification would require a separate,
  independently validated model, which is intentionally not implemented.
