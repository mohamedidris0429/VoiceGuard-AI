# Testing

## Commands

```powershell
# Backend - fast suite (SQLite, no external services)
cd backend
.venv\Scripts\python.exe -m pytest

# Backend - same suite against PostgreSQL
.venv\Scripts\python.exe -c "import psycopg; psycopg.connect('host=127.0.0.1 port=5433 user=voiceguard dbname=postgres', autocommit=True).execute('CREATE DATABASE voiceguard_test')"
$env:TEST_DATABASE_URL = "postgresql+psycopg://voiceguard:voiceguard@127.0.0.1:5433/voiceguard_test"
.venv\Scripts\python.exe -m pytest

# Real model inference (needs the cached checkpoint)
$env:VOICEGUARD_RUN_MODEL_TESTS = "1"
.venv\Scripts\python.exe -m pytest tests/test_ai.py -m slow

# Frontend unit tests and production build
cd frontend
npx vitest run
npm run build
```

`tests/conftest.py` points `DATABASE_URL` at a temporary SQLite file unless `TEST_DATABASE_URL` is set,
creates the schema with `Base.metadata.create_all`, truncates tables before each test and neutralises the
rate limiter. The detector is replaced with a deterministic stub for pipeline tests, so the fast suite needs
no network and no model weights.

## Coverage map

| Test file | Covers |
| --- | --- |
| `tests/test_auth.py` | Registration, duplicate email (409), weak password / invalid email (422), login success, wrong password (401, generic message), unknown email, protected route without token, invalid token, `/me`, profile update with preference whitelist, password change flow (old password rejected after change), bcrypt hash stored (not plain text) |
| `tests/test_audio.py` | Valid WAV upload, auth required, unsupported extension (415), non-audio content with `.wav` (415), MP3 content declared as WAV (mismatch), empty file, too-short audio (422), oversized upload (413), MP3 upload, analyse with stub (status/score/model details/features), idempotent re-analysis, model-unavailable branch recorded as `unavailable`, waveform peaks, PNG spectrogram, delete removes row **and** file, limits endpoint |
| `tests/test_processing.py` | Metadata probing, too-short/missing/format-mismatch rejection, 16 kHz mono resampling, descriptive feature ranges, normalised waveform peaks, PNG spectrogram, silent audio rejection, stereo downmix |
| `tests/test_ai.py` | Label→synthetic-index resolution, error-message sanitisation (paths removed), not-loaded status, window coverage/bounds, padding of short clips, unavailable-model error, **real inference** (`-m slow`) |
| `tests/test_records.py` | History pagination without overlap, filename search, verdict/status filters, sorting, invalid filter (422), detail, analytics summary and trends (daily, confidence, duration, status), user-scoped analytics, PDF download (`%PDF` magic, content type, attachment), stable report reference, report blocked for pending analysis, cross-user 404 on every user-owned route, health + model status, comparison endpoint and its disclaimer, comparison requires two files |
| `tests/test_forensics.py` | Forensics auth (401), foreign record (404), WAV payload (metadata, waveform buckets, RMS timeline, band shares summing to 1, model status), stereo layout, MP3 file, corrupt upload rejection (422), authenticated media streaming, deleted file (410) |
| `src/tests/format.test.js` | Duration/clock/bytes/percent formatting, prediction/status labels, WAV header structure produced by the browser encoder |
| `src/tests/history-density.test.jsx` | The `compact_tables` account preference switches the history table between compact (`py-1.5`) and comfortable (`py-3`) row padding |
| `src/tests/forensics-visual.test.jsx` | Band-energy bars render each share, the RMS timeline renders its point count, and the interactive waveform reports click-to-seek positions (jsdom smoke test) |

## Recorded results

| Run | Result |
| --- | --- |
| `pytest` (SQLite) | **65 passed, 1 skipped** — 66 collected (Phase 1 added 8 forensics tests; the skipped test is the opt-in real-model test) |
| `pytest` with `TEST_DATABASE_URL` (PostgreSQL 18.6) | **57 passed, 1 skipped** (last recorded run before Phase 1) |
| `pytest tests/test_ai.py -m slow` with `VOICEGUARD_RUN_MODEL_TESTS=1` | **1 passed** — real checkpoint loaded from `.cache/huggingface`, CPU inference on the generated fixture |
| `npx vitest run` | **13 passed** (3 files, includes the Phase 1 visualisation smoke tests) |
| `npm run build` | Success — `dist/assets/index-*.js` ≈ 733 kB (205 kB gzip); the >500 kB chunk warning is pre-existing |

## End-to-end verification (real API + real model)

Performed against a running backend on `127.0.0.1:8000` with the downloaded checkpoint:

| Step | Observed |
| --- | --- |
| `POST /auth/register` / `GET /auth/me` | 201 / 200, JWT accepted |
| Upload Windows SAPI TTS clip (6.87 s WAV) | 201, `pending`, metadata read (16 kHz mono) |
| `POST /audio/analyze` (first call) | 200, `completed`, verdict **genuine**, score **0.068**, **44.0 s** incl. one-time model load |
| `POST /audio/analyze` (second call) | 200, `completed`, verdict **synthetic**, score **0.513**, **0.5 s** |
| `GET /audio/{id}/waveform` | 200, peak array |
| `GET /audio/{id}/spectrogram` | 200, `image/png`, ~17–19 kB |
| `GET /reports/{id}/download` | 200, `%PDF-`, 5.1 kB, attachment filename |
| `GET /history` / `GET /analytics/summary` | totals matched the two stored rows |
| Second account reading the first account's analysis | **404** |
| `DELETE /audio/{id}` | 200, row and stored file removed |
| `GET /model/status` | `available=true`, 94,569,090 parameters, resolved revision recorded |

Interpretation note: the SAPI text-to-speech sample was classified as *genuine* (score 0.068) and a
harmonic test tone as *synthetic* (0.513). These are genuine model outputs, not a demonstration of accuracy —
no human speech recording was available in this environment and the model's published metrics were not
independently reproduced. Treat them as evidence that the pipeline runs end to end, not as an evaluation.

### Phase 1 forensics verification (local run, real API + PostgreSQL)

| Step | Observed |
| --- | --- |
| `GET /api/health` | 200, `database=connected` |
| Register a fresh account | 201, JWT accepted |
| Upload `storage/samples/voiced-tone.wav` | 201, `pending`, 4.0 s |
| `GET /api/forensics/{id}` | 200 — 16 kHz mono WAV, 64,000 frames, 600 waveform peaks, 126 RMS points, 6 bands summing to 1.000, centroid 616.8 Hz, `model.status=pending` |
| `GET /api/forensics/{id}/media` | 200, `audio/wav`, body starts `RIFF` |
| Forensics / media without a token | 401 / 401 |
| Second account reading the first account's record | 404 |
| `GET /api/audio/{id}/spectrogram` | 200, `image/png`, 18,874 bytes |
| `GET /api/history`, `/api/analytics/summary`, `/api/model/status` | 200 / 200 / 200 |
| `DELETE /api/audio/{id}` | 200 |

The model panel reads the stored record only; the workspace never runs new inference, so this sample
stays `pending` until analysis is run from the analysis page. This is intentional, not a failure.

## Browser-dependent behaviour

- **Microphone recording** requires a real browser with `MediaRecorder` and a microphone permission prompt.
  It was implemented and the WAV encoder is unit-tested, but the recording flow itself is not covered by an
  automated test (it needs user-granted hardware permission). Verify manually: Dashboard → Live recording →
  Start → allow the microphone → Stop → Analyse.
- Charts, responsive layouts and navigation were verified by a production build and a successful dev-server
  render; no browser automation suite (Playwright/Cypress) is included in this project.

## Gaps and limitations

- No CI pipeline is configured; all results above were produced locally.
- The classifier's accuracy was not re-measured on ASVspoof/WaveFake; only the integration was validated.
- The in-process rate limiter is single-process only (documented in `docs/ARCHITECTURE.md`).
- Tests never assert a specific verdict for real audio, because that would encode a guess as an expectation.
