# VoiceGuard AI — project progress

Last updated: 2026-11-22 (Phases 3–11 complete)

## Phase status

| Phase | Scope | Status |
| --- | --- | --- |
| 1 | Audio forensics workspace (signal measurements, spectrogram, playback) | Complete, approved |
| 2 | Audio segment-level analysis + scope hardening | Complete, 28 tests |
| 3 | Forensic enhancements (quality, metadata, segment signal) | Complete, 12 tests |
| 4 | Near-real-time chunked analysis | Complete, 14 tests |
| 5 | Detector evaluation harness | Harness complete; metrics blocked (no dataset) |
| 6 | Dashboard, history, segment timeline | Complete |
| 7 | PDF reports with coverage/quality | Complete, 3 tests |
| 8 | Security and data management | Complete, 6 tests |
| 9 | Frontend/backend integration audit | Complete; browser flow not exercised |
| 10 | Full QA | 137 passed, 1 skipped (SQLite + PostgreSQL) |
| 11 | Performance and deployment docs | Complete; no deployment performed |

Phase 1 was not redesigned: its endpoints, schemas, models and the frontend are
unchanged, and every Phase 2 database change is additive.

---

## Phase 2 — audio segment-level analysis

### What was built

Each stored recording can be scored segment by segment with the **existing real
detector** (`get_detector().predict(waveform, sample_rate)`). There is no second
model, no stub and no placeholder prediction anywhere in the request path.

- `plan_segments(duration_s, window=4.0, hop=2.0, min_duration=1.0)` builds
  overlapping segments; `window` is clamped to `0.5–30 s`, `hop` to
  `0.1–window`; the **final segment is clamped to the real duration**; segments
  shorter than `min_duration` are planned as `unsupported` and never scored;
  more than 60 segments is a `422`.
- Each supported segment is scored independently, in order, and persisted.
- Explicit non-scored states instead of invented output: `unsupported` (too
  short, empty or silent) and `error` (that segment's inference failed). Their
  `label`/`score` stay `NULL`.
- Audit metadata in `audio_analyses.segment_meta`: window, hop, overlap, sample
  rate, total duration, segment count, model id/version, aggregate, caveat.
- Honest aggregation over completed segments only: duration-weighted score,
  coverage seconds/ratio, excluded count, method, `whole_file_reliable`. The
  stored whole-file score is never overwritten.
- Idempotent persistence: repeat `POST` without `force` returns stored rows
  (`cached: true`) with no inference; `force=true` replaces them in one
  transaction. Unique `(analysis_id, segment_index)` prevents duplicates.
- Model unavailable → `409` and **no rows written**.

### Files created

| File | Purpose |
| --- | --- |
| `backend/app/services/segment_service.py` | planning, per-segment inference, aggregation, persistence |
| `backend/app/schemas/segments.py` | `SegmentOut`, `SegmentAggregateOut`, `SegmentsOut` |
| `backend/alembic/versions/0002_analysis_segments.py` | `analysis_segments` + `segment_meta` |
| `backend/tests/test_segments.py` | 28 tests |
| `docs/PHASE_2_SEGMENTS.md` | design, aggregation, caveats |
| `storage/live_segments_check.py` | live end-to-end verification script (not application code) |

### Files modified

| File | Change |
| --- | --- |
| `backend/app/models/analysis.py` | `AnalysisSegment` model, `SEGMENT_*` states, `segment_meta`, cascade relationship |
| `backend/app/models/__init__.py` | export `AnalysisSegment` |
| `backend/app/core/config.py` | `segment_window_seconds` (4.0), `segment_hop_seconds` (2.0) — env-overridable |
| `backend/app/api/routes_forensics.py` | added `GET` + `POST /{analysis_id}/segments`; Phase 1 routes untouched |
| `docs/API.md` | segment endpoints documented |
| `PROJECT_PROGRESS.md` | this file |

Frontend: **no changes**. `.env` was not modified.

### Database

Migration **`0002_segments`**, down_revision `0001_initial` (initial migration
untouched). Applied to the local PostgreSQL 18 cluster on port 5433;
`alembic current` → `0002_segments (head)`.

- `analysis_segments`: `id`, `analysis_id` (FK → `audio_analyses.id`, `ON DELETE
  CASCADE`), `segment_index`, `start_seconds`, `end_seconds`, `state`, `label`,
  `score`, `reason`, `model_name`, `model_version`, `created_at`.
- `UNIQUE (analysis_id, segment_index)` → `uq_analysis_segments_analysis_index`.
- Indexes: `ix_analysis_segments_analysis_id`,
  `ix_analysis_segments_analysis_order (analysis_id, segment_index)`.
- `audio_analyses.segment_meta`: nullable JSON.
- Downgrade drops the indexes, the table and the column.

Verified in PostgreSQL `information_schema`: the twelve columns above exist in
that order, and deleting an analysis leaves **0** segment rows (cascade).

### API endpoints added

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/api/forensics/{analysis_id}/segments` | stored result; `200 computed:false` before any run |
| POST | `/api/forensics/{analysis_id}/segments` | `window_seconds`, `hop_seconds`, `force` |

`401` anonymous · `404` missing/foreign analysis · `409` model unavailable
(nothing stored) · `410` audio file removed · `422` invalid plan/duration or
> 60 segments.

### Model

`Vansh180/deepfake-audio-wav2vec2` (MIT, 94,569,090 params, CPU, 16 kHz mono),
resolved live to `Vansh180/deepfake-audio-wav2vec2@e1197e2063`. Threshold 0.5.

### Tests and results

| Check | Result |
| --- | --- |
| `pytest tests/test_segments.py` (targeted) | **28 passed** |
| Full backend suite, SQLite | **93 passed, 1 skipped** (20.76 s) |
| Full backend suite, PostgreSQL (`TEST_DATABASE_URL`) | **93 passed, 1 skipped** (20.53 s) |
| Baseline before Phase 2 | 65 passed, 1 skipped |
| Migration validation (`upgrade head` → `downgrade 0001_initial` → `upgrade head`) | all three succeeded; `alembic current` → `0002_segments (head)` |
| Frontend `npm run build` | success (pre-existing >500 kB chunk warning; no frontend files changed) |

Test coverage: planning + overlapping windows, clamped final segment, short-tail
`unsupported`, audio shorter than the window, hop clamping, duration-weighted
aggregation, exclusion/coverage, persistence, `GET` before/after compute,
idempotent cached repeat, `force` without duplicates, silent segments never sent
to the detector, short recording, auth, cross-user ownership on both methods,
`410` missing media, `409` model unavailable with nothing stored, whole-file
score untouched, parameter bounds and the segment-count limit.

### Live end-to-end verification

`storage/live_segments_check.py` against the running API + PostgreSQL + the real
model, sample `storage/samples/synthetic-tts.wav` (6.8683 s):

| Check | Result |
| --- | --- |
| `/api/health` | `200`, `database=connected` |
| register / upload | `201` / `201` |
| `GET …/segments` before compute | `200`, `computed=false` |
| `POST /api/audio/analyze` (real model) | `200`, `completed`, `0.06836`, `genuine` |
| `POST …/segments?window_seconds=2&hop_seconds=1` | `200`, 6 segments, all `done` |
| segments | `[0,2] 0.48975` · `[1,3] 0.384658` · `[2,4] 0.061174` · `[3,5] 0.065008` · `[4,6] 0.061732` · `[5,6.8683] 0.093187` |
| aggregate | `0.193688` (`genuine`), coverage `6.868 s`, ratio `1.0`, 0 excluded, `whole_file_reliable=true` |
| repeat `POST` | `200`, `cached=true`, 6 segments, no second inference |
| Phase 1 `GET /api/forensics/{id}` after segment run | `200`, `completed`, 6 bands |
| anonymous `GET` | `401` |
| other user `GET` / `POST` | `404` / `404` |
| delete analysis → `GET …/segments` | `200` → `404` (cascade) |

Throwaway accounts from the live run were deleted afterwards.

### Hardening after the Phase 2 review

- `aggregate.label` is the whole-file verdict and is **`null` unless the aggregate
  is reliable**. `aggregate.scored_label` keeps the diagnostic label of the scored
  segments, `scope` is `whole_file` / `partial`, and `reliability_note` explains
  why a result is partial. Segment rows, scores, labels and states are unchanged.
- The rule is enforced twice: in `segment_service.aggregate_segments` and by a
  Pydantic `model_validator` on `SegmentAggregateOut`, so a stored aggregate from
  an older build is normalised on read instead of surfacing a partial result as a
  whole-file verdict.
- Caveat grammar fixed: "does not prove that audio is genuine".
- `docs/API.md` now documents `whole_file_reliable`, the 95 % threshold,
  `excluded_segments`, and that an aggregate score (and `scored_label`) can exist
  even when coverage is insufficient.
- 5 new tests: low coverage, partial tail, aggregate without any score, reliable
  label contract, and the response contract. No schema or migration change, no
  Phase 1 change, no frontend change.

### Known limitations

1. Segment scores are probabilistic model outputs, not proof of authenticity per
   segment. An aggregate over partial coverage is not a whole-file verdict:
   `label` is `null`, `scope` is `partial`, and `coverage_ratio` /
   `whole_file_reliable` / `reliability_note` disclose why. A client that renders
   its own verdict from `score` alone can still misrepresent a partial result —
   it must check `scope` or `whole_file_reliable`.
2. The detector always feeds a fixed 4 s tensor: segments shorter than
   `MODEL_WINDOW_SECONDS` are zero-padded by the existing windowing code, so a
   1–2 s segment score is not a pure short-window measurement.
3. Segment boundaries follow the hop, not speech activity; a segment can straddle
   a pause or a speaker change.
4. Inference is sequential per segment on CPU (bounded at 60 segments/request).
5. No frontend UI for segments — backend only, as specified. The Phase 1
   forensics UI has still never been inspected in a browser (build, API and unit
   tests only).
6. `/api/health` reports `model_available: false` until the model is first loaded
   or probed (pre-existing; use `/api/model/status?load=true`).
7. No Git repository exists, so there is no commit/rollback for Phase 2; the only
   backup is `storage/backups/pre-phase1-20261119-195608/`.
8. `qrcode` is not installed — only relevant if a later phase adds QR codes.

### Blockers

None.

### Phases 3–11 summary

All remaining phases are implemented; per-phase detail is in `docs/PHASE_3_REPORT.md`
through `docs/PHASE_11_REPORT.md`, with deployment steps in
`docs/DEPLOYMENT_GUIDE.md`.

Added after Phase 2:

| Area | Files |
| --- | --- |
| Signal quality + per-window forensic metrics | `backend/app/services/forensic_service.py`, `GET /forensics/{id}/segment-signal` |
| Near-real-time chunked analysis | `backend/app/services/stream_service.py`, `backend/app/api/routes_stream.py`, `frontend/src/pages/LivePage.jsx` |
| Detector evaluation harness | `backend/app/services/evaluation_service.py`, `backend/scripts/evaluate_model.py` |
| Segment timeline UI | `frontend/src/components/segments.jsx` |
| Reports with coverage/quality | `backend/app/services/report_service.py`, `backend/app/api/routes_reports.py` |
| Security headers + rate limits | `backend/app/main.py`, `routes_forensics.py`, `routes_reports.py` |

No database migration was added after `0002_segments`; all new data is computed on
request or held in memory. Phase 1 and Phase 2 endpoints remain behaviour-compatible.

Tests: 137 passed, 1 skipped on both SQLite and PostgreSQL; `npm run build` succeeds.
Known gaps: no labelled evaluation dataset, no browser/microphone run, single-worker
assumptions for rate limiting and live sessions.

### Commands used

```powershell
cd F:\sih\backend
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest tests\test_segments.py
.\.venv\Scripts\python.exe -m pytest
$env:TEST_DATABASE_URL="postgresql+psycopg://voiceguard:voiceguard@127.0.0.1:5433/voiceguard_test"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m alembic downgrade 0001_initial
.\.venv\Scripts\python.exe -m alembic upgrade head

# run the API and the live check
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
cd ..\storage; ..\backend\.venv\Scripts\python.exe live_segments_check.py
```
