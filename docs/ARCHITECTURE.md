# Architecture

## Components

| Layer | Implementation | Responsibility |
| --- | --- | --- |
| SPA | React 18 + Vite + Tailwind | Rendering, client validation, recording, charts |
| API | FastAPI + Pydantic | Validation, auth, orchestration, OpenAPI |
| Domain services | `app/services/*` | Storage, decoding/features, analysis orchestration, PDF |
| Forensics | `app/api/routes_forensics.py` + `audio_service.forensic_signal` + `src/pages/ForensicsPage.jsx` | Bounded signal measurements (waveform, RMS, band energy), authenticated playback, stored model record |
| AI | `app/ai/detector.py` | Lazy model load, windowed CPU inference, honest failure |
| Persistence | SQLAlchemy 2 + Alembic + PostgreSQL | Users, analyses, reports, migrations |
| Files | `storage/audio/<user>/<uuid>.<ext>` | Private recordings with opaque names |

The frontend never talks to PostgreSQL or the model directly; the API is the only entry point.

## Analysis sequence

```
React              FastAPI                     Services                    Model / DB
  │  POST /audio/upload (multipart)
  ├────────────────▶│ rate limit + auth
  │                 ├─ storage_service.save_upload ──▶ validate header/size, write UUID file
  │                 ├─ audio_service.probe_audio ───▶ libsndfile metadata + limits
  │                 └─ INSERT audio_analyses (pending) ───────────────────▶ PostgreSQL
  │◀── AnalysisOut (pending, metadata) ────────────
  │  POST /audio/analyze {analysis_id}
  ├────────────────▶│ ownership check
  │                 ├─ audio_service.load_model_input ─▶ librosa 16 kHz mono + trim
  │                 ├─ detector.predict ──────────────▶ wav2vec2, ≤3×4 s windows, mean score
  │                 ├─ audio_service.extract_features ─▶ MFCC/centroid/ZCR/RMS (descriptive)
  │                 └─ UPDATE row (completed | unavailable | failed) ────▶ PostgreSQL
  │◀── AnalysisOut (verdict, score, model details, features)
  │  GET /audio/{id}/waveform, /spectrogram  → derived on demand from the stored file
  │  GET /reports/{id}/download              → ReportLab PDF from the stored row
```

## Design decisions

**Two-step upload/analyse.** Upload and inference are separate endpoints so the UI can show real upload
progress and a distinct “model working” state, and so a failed inference does not lose the uploaded file.
`analyze` is idempotent for completed rows.

**Server-side validation is authoritative.** Client checks (extension, size, duration) are a convenience;
the backend re-validates the container header, decodes metadata with libsndfile, enforces the duration and
sample-rate window and only then stores the file.

**Storage references are opaque.** The database stores a relative reference (`<user_id>/<uuid>.ext`).
Resolution is confined to the audio directory via `Path.resolve()` checks, and the reference is excluded
from every response schema.

**Model lifecycle.** A process-wide singleton loads on first use behind a lock, sets `torch.set_num_threads`,
disables gradients, and caches the resolved commit hash for model-version traceability. Load failures are
remembered for 120 s to avoid hammering a broken network, then retried.

**Verdicts are never back-filled.** There is no random or default score path. Missing model ⇒ status
`unavailable` with a reason, which the UI renders distinctly from both `genuine` and `synthetic`.

**Honest analytics.** Every panel aggregates `audio_analyses` for the authenticated user (SQL `COUNT`,
`AVG`, `DATE` grouping, filtered buckets). Empty states show instead of fabricated zeros beyond the real
zero counts.

**Deliberate non-features.** No speaker verification, no continuous real-time monitoring, no crowd-sourced
score sharing — all would be unsupported claims given the implemented model.

## Database model

```
users ──1:N── audio_analyses ──1:1── reports
  id              id                   id
  name            user_id (FK CASCADE) user_id (FK CASCADE)
  email (unique)  filename             analysis_id (FK CASCADE, unique)
  password_hash   stored_file_reference report_reference (unique)
  preferences     audio_duration/sample_rate/channels/format/size
  created_at      source
  updated_at      predicted_class, model_score, model_version
                  analysis_status, failure_reason, analysis_duration_ms
                  audio_features (JSON), model_details (JSON)
                  created_at, updated_at
```

Migration `0001_initial_schema` creates the tables and all indexes; `alembic upgrade head` is the supported
path (the app never calls `create_all` in production paths).

## Security model

- Authentication: bcrypt (cost 12) + JWT (`sub`, `iat`, `exp`, `iss`), integer-subject parsing, user lookup.
- Authorisation: `get_current_user` dependency plus `get_owned_analysis`, which returns 404 for both
  missing and foreign records.
- Input handling: Pydantic schemas, enum-style regex patterns for filters/sort fields, upload limits,
  container sniffing, filename sanitisation, UUID storage names.
- Transport surface: restrictive CORS, `X-Content-Type-Options`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `Cache-Control: no-store` on API responses.
- Failures: `AppError` hierarchy maps to safe messages; unexpected exceptions are logged with context and
  returned as a generic 500.
- Abuse control: in-process sliding-window limiter keyed by IP (auth) and user (analysis).
- Secrets: environment variables only; `.env`, `storage/`, and the model cache are git-ignored.

## Extensibility

- Add a model: implement a `predict(waveform, sample_rate) -> Prediction` adapter and swap it in
  `get_detector()`; the storage schema already records model id/version/details per row.
- Scale out: move the rate limiter to Redis and the model to a dedicated inference worker; the API contract
  stays identical.
- Add speaker verification: a separate endpoint and model are required; the comparison page must not claim
  identity without it.
