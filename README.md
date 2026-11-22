# VoiceGuard AI

**AI-powered detection of voice-cloning / synthetic speech.**
SIH problem statement **SIH26104** — _AI-Powered Real-Time Detection and Prevention of Voice Cloning Impersonation Attacks._

VoiceGuard AI is a full-stack application: a React dashboard, a FastAPI service, PostgreSQL persistence, a
real audio-processing pipeline and **real CPU inference** with a pretrained anti-spoofing model. Every
number shown in the UI comes from the database or from the model — nothing is simulated.

> **Honest capability statement.** The application analyses a *finished* recording and estimates the
> probability that the speech is synthetic. It is not continuous real-time monitoring, it does not identify
> a speaker, and a verdict is **never proof**. If the model cannot be loaded the analysis is recorded as
> **unavailable** — the system never invents a prediction.

---

## Contents

- [Features](#features)
- [Technology stack](#technology-stack)
- [System architecture](#system-architecture)
- [Repository layout](#repository-layout)
- [Prerequisites](#prerequisites)
- [Quick start on Windows](#quick-start-on-windows)
- [Backend setup](#backend-setup)
- [PostgreSQL configuration](#postgresql-configuration)
- [Environment configuration](#environment-configuration)
- [AI model setup](#ai-model-setup)
- [Running the application](#running-the-application)
- [API documentation](#api-documentation)
- [Testing](#testing)
- [Low-memory configuration](#low-memory-configuration)
- [Troubleshooting](#troubleshooting)
- [Security notes](#security-notes)
- [Limitations and ethics](#limitations-and-ethics)
- [Credits and licences](#credits-and-licences)

---

## Features

| Module | What it does |
| --- | --- |
| Authentication | Registration, login, logout, JWT sessions, bcrypt password hashing, protected routes, profile and password change |
| Dashboard | Totals, genuine/synthetic counts, average confidence, 14-day trend, classification distribution, recent activity, API/DB/model status |
| Audio upload | Drag & drop or browse, WAV/MP3 only, header + size + duration validation, upload progress, playback preview, metadata |
| Audio processing | librosa/soundfile decoding, mono conversion, resampling to 16 kHz, silence trim, bounded windowing, descriptive features (MFCC, spectral centroid/roll-off/bandwidth, ZCR, RMS) |
| AI detection | Real wav2vec 2.0 spoof classifier on CPU, per-window scoring, model version, threshold, explicit "unavailable" state |
| Results | Verdict, probability, confidence, metadata, model details, waveform, spectrogram, descriptive features |
| Audio forensics | Dedicated workspace per analysis: authenticated playback, timeline seeking on an interactive waveform, spectrogram, loudness-over-time and frequency-band charts, container metadata and the stored model record — explicitly labelled as signal visualisation, not evidence |
| Live recording | MediaRecorder capture, permission handling, timer, playback, re-record, browser-side WAV encoding, same backend pipeline |
| Analytics | Activity charts, classification distribution, confidence histogram, duration buckets, status breakdown — all from stored rows |
| History | Search, status/verdict filters, sorting, pagination, view, PDF download, delete |
| Comparison | Two recordings analysed independently, side-by-side metadata, scores and spectrograms (no speaker verification claimed) |
| PDF reports | Branded ReportLab report with report ID, analysis details, model information and limitations |
| Profile & settings | Name, preferences, password change, account summary, sign out |
| System status | API health, PostgreSQL connectivity, model availability with manual preload, security controls |

---

## Technology stack

**Frontend** — React 18, Vite 5, Tailwind CSS 3, React Router 6, Recharts 2, Lucide React.
**Backend** — Python 3.13, FastAPI, Uvicorn, Pydantic v2, SQLAlchemy 2, Alembic, psycopg 3, PyJWT, bcrypt, slowapi-style in-process rate limiting (custom sliding window).
**AI / audio** — PyTorch (CPU wheel), Transformers, librosa, SoundFile, NumPy.
**Database** — PostgreSQL 18 (project-local cluster on port 5433 by default; pgAdmin 4 optional).
**Reports** — ReportLab, Pillow (spectrogram rendering).
**Testing** — Pytest + FastAPI TestClient (backend), Vitest + Testing Library (frontend).

Verified on Windows 11 with Python 3.13.14, Node 24.x, PostgreSQL 18.6, torch 2.15.0+cpu,
transformers 5.23.0, librosa 1.0.1.

---

## System architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  Browser (React + Vite)                                              │
│   Auth pages · Dashboard · Upload · Record · History · Compare       │
│   Analytics · Results · Profile · System                             │
│   └── central API layer (src/services/api.js, JWT bearer tokens)     │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ HTTPS/JSON multipart
┌───────────────────────────────▼──────────────────────────────────────┐
│  FastAPI (backend/app)                                               │
│  Routers: auth · audio · history · reports · analytics · system      │
│  Dependencies: bearer auth, ownership checks, rate limiting          │
│                                                                      │
│  Services                    AI                                     │
│  ├─ storage_service  ──→     ├─ detector (lazy, thread-safe)         │
│  │   validated uploads       │   wav2vec2 spoof classifier (CPU)     │
│  ├─ audio_service            │   ≤3 × 4 s windows → mean score       │
│  │   probe · resample        └─ unavailable ⇒ recorded as such       │
│  ├─ analysis_service                                                 │
│  └─ report_service (PDF)                                             │
└──────────┬──────────────────────────────┬────────────────────────────┘
           │ SQLAlchemy 2 / psycopg 3      │ filesystem (UUID filenames)
┌──────────▼──────────────┐       ┌───────▼────────────────────────────┐
│ PostgreSQL 18           │       │ storage/audio/<user>/<uuid>.wav    │
│ users · audio_analyses  │       │ (paths never exposed to clients)   │
│ reports · alembic_ver   │       └────────────────────────────────────┘
└─────────────────────────┘
```

Request flow for an analysis: `POST /api/audio/upload` validates and stores the file, probes its container
and creates a `pending` row → `POST /api/audio/analyze` decodes to mono 16 kHz, runs inference, extracts
descriptive features and updates the row to `completed` / `unavailable` / `failed`.

---

## Repository layout

```
voiceguard-ai/                    (this repository = F:\sih)
├── frontend/
│   ├── src/
│   │   ├── components/           ui.jsx, charts.jsx, audio.jsx, verdict.jsx, forensics.jsx
│   │   ├── pages/                Login, Register, Dashboard, Upload, Record, …
│   │   ├── layouts/              AppLayout, AuthLayout
│   │   ├── services/api.js       single API layer (fetch + XHR upload progress)
│   │   ├── context/              AuthContext, ToastContext
│   │   ├── utils/                format.js, wav.js
│   │   └── tests/                Vitest unit tests
│   ├── index.html · vite.config.js · tailwind.config.js · package.json
├── backend/
│   ├── app/
│   │   ├── api/                  deps + routers
│   │   ├── core/                 config, security, errors, rate_limit
│   │   ├── models/               User, AudioAnalysis, Report
│   │   ├── schemas/              Pydantic request/response models
│   │   ├── services/             storage, audio, analysis, report
│   │   ├── ai/detector.py        pretrained model loading + inference
│   │   ├── database/             engine, session, declarative base
│   │   └── main.py               FastAPI app
│   ├── alembic/                  migrations (0001_initial)
│   ├── tests/                    pytest suite
│   ├── requirements.txt · .env.example · pytest.ini
├── storage/                      audio/ reports/ tmp/ (git-ignored)
│   └── .pgdata/                  project-local PostgreSQL cluster (git-ignored)
├── scripts/                      setup_database.ps1, generate_samples.py
├── docs/                         ARCHITECTURE, AI_MODEL, API, TESTING, PHASE_1_FORENSICS
├── .cache/huggingface/           model cache (git-ignored, ~378 MB)
└── README.md
```

---

## Prerequisites

- **Windows 10/11** with PowerShell 5.1+
- **Python 3.11+** (tested on 3.13) — `python --version`
- **Node.js 18+** with npm (tested on Node 24)
- **PostgreSQL 18** installed (`C:\Program Files\PostgreSQL\18\bin`). pgAdmin 4 is optional.
- ~1.5 GB free disk for dependencies + model, ~1.5 GB RAM available during inference.
- Internet access **only** for the first model download (afterwards it runs offline).

---

## Quick start on Windows

```powershell
# 1. From the project root (F:\sih)

# 2. Backend virtual environment + dependencies
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
backend\.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

# 3. Frontend dependencies
cd frontend
npm install
cd ..

# 4. Database: create + start the project-local cluster, create DB, migrate
powershell -ExecutionPolicy Bypass -File scripts\setup_database.ps1

# 5. Backend (terminal A)
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# 6. Frontend (terminal B)
cd frontend
npm run dev
```

Open <http://127.0.0.1:5173>, create an account, upload a WAV/MP3, and run the analysis.
Swagger UI: <http://127.0.0.1:8000/api/docs>.

Optional — generate test samples (including a Windows TTS clip):

```powershell
backend\.venv\Scripts\python.exe scripts\generate_samples.py
```

---

## Backend setup

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip

# PyTorch CPU wheel first (much smaller than the CUDA build)
.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu

.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env      # then edit if needed
```

Run from `backend/` so the relative paths in `.env` resolve correctly (the app also resolves them
against `backend/` if you launch from elsewhere):

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

---

## PostgreSQL configuration

### Option A — project-local cluster (default, recommended for the demo)

`scripts\setup_database.ps1` initialises a PostgreSQL 18 cluster in `storage\.pgdata`, listens only on
`127.0.0.1:5433`, creates the `voiceguard` database and runs Alembic. This leaves any existing
PostgreSQL service on port 5432 untouched.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_database.ps1
```

Manual equivalent:

```powershell
$pg = "C:\Program Files\PostgreSQL\18\bin"
& "$pg\initdb.exe" -D "F:\sih\storage\.pgdata" -U voiceguard -A trust -E UTF8 --locale=C
& "$pg\postgres.exe" -D "F:\sih\storage\.pgdata" -p 5433 -c listen_addresses=127.0.0.1
# in a second shell:
& "$pg\createdb.exe" -h 127.0.0.1 -p 5433 -U voiceguard voiceguard
cd backend; .venv\Scripts\python.exe -m alembic upgrade head
```

`DATABASE_URL=postgresql+psycopg://voiceguard:voiceguard@127.0.0.1:5433/voiceguard`

### Option B — your existing PostgreSQL service

Create a role and database, then point `DATABASE_URL` at it:

```sql
CREATE ROLE voiceguard LOGIN PASSWORD 'choose-a-strong-password';
CREATE DATABASE voiceguard OWNER voiceguard;
```

```powershell
cd backend
.venv\Scripts\python.exe -m alembic upgrade head   # after updating DATABASE_URL
```

pgAdmin 4: register a server with host `127.0.0.1`, port `5433` (or `5432`), database `voiceguard`,
user `voiceguard`.

### Schema

| Table | Key columns |
| --- | --- |
| `users` | id, name, **unique** email, password_hash, preferences, created_at, updated_at |
| `audio_analyses` | id, **FK** user_id → users (CASCADE), filename, stored_file_reference, audio_duration, sample_rate, channels, file_format, file_size_bytes, source, predicted_class, model_score, model_version, analysis_status, failure_reason, analysis_duration_ms, audio_features (JSON), model_details (JSON), created_at, updated_at |
| `reports` | id, **FK** user_id, **unique FK** analysis_id, unique report_reference, created_at |

Indexes: `users.email` (unique), `audio_analyses(user_id)`, `(user_id, created_at)`,
`(user_id, analysis_status)`, `(user_id, predicted_class)`, `reports.analysis_id` (unique),
`reports.report_reference` (unique).

Migrations live in `backend/alembic/versions/`; `alembic upgrade head` is the supported way to create the schema.

---

## Environment configuration

`backend/.env` (copy from `backend/.env.example` — never commit the real file):

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+psycopg://voiceguard:voiceguard@127.0.0.1:5433/voiceguard` | SQLAlchemy URL |
| `SECRET_KEY` | _empty_ | JWT signing key. Empty ⇒ a random key is generated once in `storage/.jwt_secret` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `720` | Token lifetime |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Allowed browser origins |
| `STORAGE_DIR` | `../storage` | Audio/report storage root (resolved against `backend/`) |
| `MAX_UPLOAD_MB` | `20` | Upload size limit |
| `MIN_AUDIO_SECONDS` / `MAX_AUDIO_SECONDS` | `1` / `60` | Accepted duration window |
| `MODEL_ID` | `Vansh180/deepfake-audio-wav2vec2` | Pretrained classifier |
| `MODEL_CACHE_DIR` | `../.cache/huggingface` | Where weights are cached |
| `MODEL_SAMPLE_RATE` | `16000` | Model input rate |
| `MODEL_WINDOW_SECONDS` / `MODEL_MAX_WINDOWS` | `4` / `3` | Windowing for long clips |
| `MODEL_THREADS` | `0` | `0` ⇒ `min(4, cpu_count)` |
| `MODEL_OFFLINE` | `0` | `1` ⇒ never touch the network (cache only) |
| `SYNTHETIC_THRESHOLD` | `0.5` | Decision threshold on the synthetic probability |
| `RATE_LIMIT_AUTH` / `RATE_LIMIT_ANALYSIS` | `10/60` / `20/60` | Requests per window |

`frontend/.env.local` (optional):

```
VITE_API_BASE_URL=http://127.0.0.1:8000/api
```

---

## AI model setup

**Selected model:** [`Vansh180/deepfake-audio-wav2vec2`](https://huggingface.co/Vansh180/deepfake-audio-wav2vec2)

| Property | Value |
| --- | --- |
| Architecture | `Wav2Vec2ForSequenceClassification` (wav2vec 2.0 base, 12 layers) |
| Parameters | 94,569,090 (~94.6 M), float32 |
| Checkpoint size | ~378 MB (`model.safetensors`) |
| Licence | MIT |
| Labels | `0 = real`, `1 = fake` |
| Task | Binary bonafide vs spoof speech classification |
| Training data | Balanced subset of ASVspoof 2021 PA (replay/spoofed speech) |
| Reported metrics | 92.8% accuracy, 89.7% precision, 88.0% recall (self-reported by the model author, **not independently verified**) |
| Input | Raw mono waveform, 16 kHz |
| Inference | CPU, PyTorch; ~1–3 s per 4 s window on a modern laptop CPU |

Downloaded automatically on first use into `.cache/huggingface/`; set `HF_HUB_DISABLE_XET=1` if your
network blocks the Xet transfer backend (the backend sets this by default). For a fully offline run after
the first download, set `MODEL_OFFLINE=1`.

**How a score is produced** (`backend/app/ai/detector.py`):

1. Audio is decoded to mono float32 at 16 kHz and lightly trimmed of leading/trailing silence.
2. Up to three evenly-spaced 4-second windows are taken (shorter clips are zero-padded).
3. Each window is normalised with the model's feature extractor and classified.
4. The per-window softmax probabilities for the `fake` class are averaged.
5. `synthetic_probability ≥ SYNTHETIC_THRESHOLD` ⇒ “Potentially synthetic”; otherwise “Likely genuine”.
6. Model ID, resolved commit revision, labels, threshold, window scores and timing are stored with the row.

The classifier’s raw output is the only thing that decides the verdict. Handcrafted features are stored
separately for transparency and are **not** used as evidence.

See [`docs/AI_MODEL.md`](docs/AI_MODEL.md) for provenance, evaluation context and dataset licensing notes.

---

## Running the application

| Service | Command | URL |
| --- | --- | --- |
| PostgreSQL | `powershell -File scripts\setup_database.ps1` (idempotent) | `127.0.0.1:5433` |
| Backend | `cd backend; .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000` | <http://127.0.0.1:8000> |
| Frontend | `cd frontend; npm run dev` | <http://127.0.0.1:5173> |
| Swagger | — | <http://127.0.0.1:8000/api/docs> |

Production build of the frontend: `cd frontend; npm run build` (output in `frontend/dist`).

---

## API documentation

Base prefix `/api`. Interactive docs at `/api/docs` (Swagger) and `/api/redoc`. Full reference:
[`docs/API.md`](docs/API.md).

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | `/api/auth/register` | Create account (returns JWT) |
| POST | `/api/auth/login` | Sign in (returns JWT) |
| GET | `/api/auth/me` | Current user |
| PATCH | `/api/auth/me` | Update name / preferences |
| POST | `/api/auth/change-password` | Change password |
| POST | `/api/audio/upload` | Validate + store a WAV/MP3, create pending analysis |
| POST | `/api/audio/analyze` | Run inference for an analysis id |
| GET | `/api/audio/{id}` | Analysis detail |
| GET | `/api/audio/{id}/waveform` | Downsampled peak envelope |
| GET | `/api/audio/{id}/spectrogram` | PNG mel spectrogram |
| DELETE | `/api/audio/{id}` | Delete record + stored file |
| POST | `/api/audio/compare` | Analyse two files independently |
| GET | `/api/audio/limits/info` | Active upload constraints |
| GET | `/api/forensics/{analysis_id}` | Forensics workspace: metadata, waveform, RMS/band charts, stored model record |
| GET | `/api/forensics/{analysis_id}/media` | Authenticated playback of the stored recording |
| GET | `/api/history` | Search / filter / sort / paginate |
| GET | `/api/history/{id}` | Single history record |
| GET | `/api/reports/{analysis_id}/download` | PDF report |
| GET | `/api/reports/{analysis_id}/metadata` | Report reference |
| GET | `/api/analytics/summary` | Aggregate statistics |
| GET | `/api/analytics/trends?days=14` | Daily series + distributions |
| GET | `/api/health` | API + DB + model health |
| GET | `/api/model/status?load=true` | Model status, optional preload |

All audio/history/report/analytics endpoints require `Authorization: Bearer <token>` and are scoped to
the caller. Another user's record returns **404**, not 403, to avoid record enumeration.

Example:

```powershell
$token = (Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/auth/login `
  -ContentType 'application/json' `
  -Body '{"email":"you@example.com","password":"Str0ngPass123"}').access_token

curl.exe -H "Authorization: Bearer $token" -F "file=@storage/samples/voiced-tone.wav" `
  http://127.0.0.1:8000/api/audio/upload
```

---

## Testing

```powershell
# Backend (SQLite test database by default, no server needed)  -> 65 passed, 1 skipped
cd backend
.venv\Scripts\python.exe -m pytest

# Backend against PostgreSQL 18 -> 65 passed, 1 skipped
$env:TEST_DATABASE_URL = "postgresql+psycopg://voiceguard:voiceguard@127.0.0.1:5433/voiceguard_test"
.venv\Scripts\python.exe -m pytest

# Real-model inference test (downloads/uses the checkpoint)
$env:VOICEGUARD_RUN_MODEL_TESTS = "1"
.venv\Scripts\python.exe -m pytest tests/test_ai.py -m slow

# Frontend
cd frontend
npx vitest run
npm run build
```

See [`docs/TESTING.md`](docs/TESTING.md) for the coverage map and recorded results.

---

## Low-memory configuration

Tuned for a 4 GB machine with no GPU:

- PyTorch **CPU-only** wheel; no CUDA, no training, no large language models.
- Model is loaded **lazily** on the first analysis and reused; a single 94.6 M-parameter model in float32.
- Inference is wrapped in `torch.inference_mode()` with gradients disabled and thread count capped at 4.
- Audio is decoded straight to 16 kHz mono (a 60 s clip is ~3.8 MB), features use at most 30 s.
- Uploads are streamed to disk in 256 KiB chunks and never held in memory; size ≤ 20 MB, duration ≤ 60 s.
- SQLAlchemy pool limited to 5 connections; PostgreSQL `shared_buffers` 64 MB, `max_connections` 20.
- No background workers, queues, containers or Redis processes.

Measured on the development machine: backend ~150 MB RSS before the model is loaded and **926 MB** with the
checkpoint resident. The first analysis takes ~44 s (one-time model load + PyTorch initialisation); later
analyses take ~0.5 s for a 4–7 s clip. Close the dev server and backend when not in use if RAM is tight.

---

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `Cannot reach the VoiceGuard AI API` | Backend not running, or `VITE_API_BASE_URL` is wrong. Start uvicorn on port 8000. |
| Registration returns 409 | Email already exists (case-insensitive). Sign in instead. |
| `503 AI detection is unavailable` | Weights could not be downloaded/loaded. Check network, then `GET /api/model/status?load=true` for the sanitised reason. |
| Model download fails with “couldn't connect” | Behind a restrictive network. Set `HF_HUB_DISABLE_XET=1` and retry, or pre-download the repo into `MODEL_CACHE_DIR` and set `MODEL_OFFLINE=1`. |
| PostgreSQL will not start via `pg_ctl` | On some Windows setups `pg_ctl` child processes fail (`0xC0000142`). Start `postgres.exe` directly (`scripts\setup_database.ps1` does this) or use your own service on 5432. |
| `connection refused` on 5433 | Cluster not started: re-run `scripts\setup_database.ps1`, or check `storage\pg.log`. |
| `alembic: relation already exists` | Schema was created by an older attempt; run `alembic stamp head` after verifying tables exist. |
| MP3 rejected as invalid | The file is not a real MP3 (header check fails) or the container is corrupt. Re-encode it. |
| Upload rejected: “too long/short” | Adjust `MIN_AUDIO_SECONDS` / `MAX_AUDIO_SECONDS`, or trim the clip. |
| Waveform/spectrogram 404 | The stored file was deleted; the analysis row still exists. Delete the record and re-analyse. |
| `422` on login/register | Request body failed validation; the message names the offending field. |
| Slow first analysis | Expected: ~378 MB of weights load once (measured ~44 s including PyTorch start-up), then each analysis is under a second for short clips. |
| Rate limited (429) | Authentication is limited to 10 requests/minute per IP; analysis to 20/minute per user. Wait for the window to pass. |

---

## Security notes

- Passwords hashed with **bcrypt** (cost 12); plain text is never stored or logged.
- JWT access tokens signed with HMAC-SHA256 using a key from `.env` or a locally generated
  `storage/.jwt_secret`; expiry enforced; invalid/expired tokens return 401.
- Every user-owned resource is fetched with an ownership predicate; foreign records return 404.
- Uploads: extension allow-list, container header sniffing, extension/content agreement, size limit,
  duration/sample-rate limits, random UUID filenames, path-traversal-safe resolution.
- Files live outside the served directory; `stored_file_reference` is never serialised to clients.
- CORS restricted to configured origins; security headers (`nosniff`, `DENY`, `no-referrer`) are added.
- Centralised exception handlers log details server-side and return safe messages to clients.
- Rate limiting on auth and analysis endpoints; request schemas reject unknown/oversized values.
- No secrets in source control — `.env` and `storage/` are git-ignored, `.env.example` contains no values.

---

## Limitations and ethics

- **Probabilistic output.** EER-style errors are real: expect false positives on unusual human speech
  and false negatives on high-quality clones or audio that has been re-encoded.
- **Domain.** The checkpoint was trained on spoofed/replayed speech; performance on unseen generators,
  languages, codecs or noisy conditions is not guaranteed.
- **Not a speaker identifier.** No speaker-verification model is implemented, so the app never claims
  two clips belong to the same person.
- **No continuous monitoring.** Recording is captured and analysed after it stops.
- **Human oversight required.** Do not use a result as the sole basis for disciplinary, legal, financial
  or safety decisions. Interpret it together with provenance, context and, where appropriate, expert review.
- Research datasets such as ASVspoof and WaveFake have their own licences and access conditions; they
  were not redistributed with this project.

---

## Credits and licences

- Application code: MIT-style educational project for SIH 2026, problem statement SIH26104.
- Model: `Vansh180/deepfake-audio-wav2vec2` (MIT), built on `facebook/wav2vec2-base` (MIT/Apache-2.0 lineage).
- Libraries: FastAPI, SQLAlchemy, Alembic, PyTorch (BSD-3), Transformers (Apache-2.0), librosa (ISC),
  SoundFile, ReportLab (BSD), React (MIT), Vite, Tailwind CSS, Recharts (MIT), Lucide (ISC).
