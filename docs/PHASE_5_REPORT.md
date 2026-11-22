# Phase 5 - AI detection improvements and evaluation

Status: **evaluation harness implemented and unit-tested; no dataset metrics are reported
because no labelled validation dataset is available in this environment.**

## Detector audit

`backend/app/ai/detector.py` (unchanged in behaviour):

* Model: `Vansh180/deepfake-audio-wav2vec2`, `Wav2Vec2ForSequenceClassification`,
  labels `real`/`fake`, 94.6 M parameters, CPU, ~378 MB checkpoint, revision recorded as
  `model_id@<commit>`.
* Input: mono 16 kHz; whole-file analysis averages up to 3 windows of 4 s; short audio is
  zero-padded by the existing windowing code.
* No fallback prediction: if weights cannot load, `ModelUnavailableError` is raised and the
  analysis is stored as `unavailable`.
* Output metadata (`model_details`) records model id, labels, threshold, aggregation,
  window count/length, raw window scores, inference time, parameter count and device.

## Evaluation tooling (new)

`backend/scripts/evaluate_model.py` + `backend/app/services/evaluation_service.py`:

```
backend/
  spoof/     *.wav|*.mp3     (label 1)
  bonafide/  *.wav|*.mp3     (label 0)

python scripts/evaluate_model.py --dataset <dir> --output ../storage/eval/report
```

* Runs the **real** detector file-by-file (no batching tricks, no synthetic scores).
* Computes accuracy, precision, recall, F1, specificity, ROC-AUC (rank-based, tie-aware) and
  the confusion matrix at a configurable threshold, plus false-positive/false-negative counts.
* Writes JSON (per-file scores + metrics) and Markdown; every artefact carries the
  disclaimer that metrics describe the supplied dataset only.
* Refuses to run on a missing or unlabelled directory (exit 2) and writes no metrics when
  no file could be scored (exit 3). It never invents values.

### Measured results

**Not available.** No labelled spoof/bonafide corpus is stored in this repository, and
downloading ASVspoof or a similar dataset was not authorised. Consequently:

* no accuracy/F1/ROC-AUC figures are claimed anywhere in the project;
* the only existing quantitative claim remains the model card's self-reported 92.8 %, which
  is presented as unverified.

To produce real numbers, point the script at a labelled corpus and attach the generated
`report.md` to this phase.

## Preprocessing

No preprocessing change was made. The requirement is to change it only when experiments
demonstrate a benefit, and without a labelled dataset no such experiment is possible. The
existing pipeline (decode → mono 16 kHz → light trim → fixed windows) is therefore preserved
and remains the fallback.

## Model regression tests

Metric math and the runner are covered without loading the 378 MB model
(`backend/tests/test_evaluation.py`, 9 tests):

* perfect separation, partial confusion, threshold sensitivity, tie-aware AUC, single-class
  AUC `None`, input validation;
* dataset discovery errors, per-file error recording, limit-per-class, JSON/Markdown output;
* CLI refuses a missing dataset and writes nothing.

`backend/tests/test_ai.py` continues to cover detector status/loading behaviour.

## Known limitations

* Supported formats: WAV and MP3 (libsndfile); 8 kHz–192 kHz input, 1–60 s duration.
* Short clips (< 4 s) are zero-padded, which is a property of the model input, not a
  measurement of that short clip.
* CPU-only; whole-file inference is sequential.
* Cross-domain generalisation, codec robustness and calibration are **unmeasured** here.
