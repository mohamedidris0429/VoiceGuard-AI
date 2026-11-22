# Phase 10 - Complete testing and QA

Status: **all executable suites pass**; items that could not run are listed explicitly.

## Environment

* Windows 11, Python virtualenv `backend/.venv`, Node/Vite frontend.
* PostgreSQL 18 on `127.0.0.1:5433`, database `voiceguard`, test DB `voiceguard_test`.
* Detector model cached at `.cache/huggingface` (offline mode enabled in tests).

## Executed commands and results

| # | command (from `backend/` unless noted) | result |
| --- | --- | --- |
| 1 | `python -m pytest tests/test_forensics_quality.py` | 12 passed |
| 2 | `python -m pytest tests/test_stream.py` | 14 passed |
| 3 | `python -m pytest tests/test_evaluation.py` | 9 passed |
| 4 | `python -m pytest tests/test_reports_phase7.py` | 3 passed |
| 5 | `python -m pytest tests/test_security.py` | 6 passed |
| 6 | `python -m pytest` (SQLite, full suite) | **137 passed, 1 skipped** in 35.82 s |
| 7 | `TEST_DATABASE_URL=postgresql+psycopg://…/voiceguard_test python -m pytest` | **137 passed, 1 skipped** in 37.08 s |
| 8 | `python -m alembic current` | `0002_segments (head)` |
| 9 | `python -m alembic upgrade head` | no-op, already at head |
| 10 | `npm run build` (from `frontend/`) | success, 7.41 s |
| 11 | `npm test` (from `frontend/`, Vitest + jsdom) | **13 passed** (3 files) in 5.65 s |

JUnit artefacts: `storage/full-phaseN.xml`, `storage/pg-phaseN.xml`
(total `tests="138"`, one skipped per run).

### The skipped test

`tests/conftest.py::mp3_file` is skipped when the installed libsndfile build has no MP3
encoder. It is an environment capability, not a product failure; MP3 **decoding** is covered
by the existing MP3 test where the encoder is available, and the upload path checks the MP3
magic header independently.

## Coverage by area

| area | tests |
| --- | --- |
| Authentication / profile / password | `test_auth.py` |
| Upload validation, decoding, limits | `test_processing.py` |
| Analysis + model integration | `test_ai.py`, `test_processing.py` |
| Forensics (Phase 1) + quality (Phase 3) | `test_forensics.py`, `test_forensics_quality.py` |
| Segments (Phase 2) + scope contract | `test_segments.py` |
| History, analytics, reports, ownership | `test_records.py`, `test_reports_phase7.py` |
| Live chunked analysis (Phase 4) | `test_stream.py` |
| Evaluation metrics (Phase 5) | `test_evaluation.py` |
| Security headers / rate limits / leakage | `test_security.py` |
| Frontend formatting, history density, forensics visual helpers | `frontend/src/tests` - 13 Vitest tests passed |

## Issues found and fixed during this phase

1. Evaluation runner ordering assumption in a test (discovery is alphabetical) - fixed the
   test, not the product.
2. PDF assertions required decoding ReportLab's ASCII85+Flate streams - test helper added;
   no product change.
3. `HistoryPage` invalid class-name expression (styling bug) - fixed in Phase 9.
4. Rate-limit test initially consumed its budget in the upload call - test adjusted to the
   real shared budget; behaviour unchanged.

## Not validated (honest gaps)

* **No labelled dataset**, so Phase 5 model accuracy/F1/ROC-AUC are not measured.
* **No browser/microphone run**: layout at real viewports, permission prompts and the
  MediaRecorder → WAV path are not confirmed end-to-end. Frontend tests run in jsdom, which
  logs an expected "canvas getContext not implemented" warning (the component guards for it).
* **No load/stress test**; concurrency, multi-worker behaviour and rate-limit fairness under
  load are unmeasured.
* **No accessibility audit** (axe/Lighthouse) was run.
* **No external security scanner** was run.
* Real-model inference during the suite is stubbed to keep tests fast; the real model path was
  exercised separately during Phase 2 live verification and is unchanged.

## Known limitations (consolidated)

1. Segment/whole-file scores are probabilistic indicators, never proof of cloning or identity.
2. Short windows (< 4 s) are zero-padded by the detector.
3. Live analysis is chunked near-real-time (≥ one chunk latency), not continuous.
4. In-process rate limiter and live-session registry assume a single worker.
5. Model evaluation on external corpora is unmeasured.
6. No bulk account deletion; deletion is per analysis.
7. PDF window tables are capped at 40 rows.
