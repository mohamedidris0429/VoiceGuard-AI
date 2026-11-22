# VoiceGuard AI API reference

Base URL: `http://127.0.0.1:8000/api`
Interactive docs: `/api/docs` (Swagger) · `/api/redoc` · schema at `/api/openapi.json`

All responses are JSON unless noted. Errors use:

```json
{ "detail": "Human readable, safe message", "code": "machine_readable_code" }
```

| Status | Meaning |
| --- | --- |
| 400 | Invalid request (`bad_request`) |
| 401 | Missing/expired/invalid token, or bad credentials (`unauthorized`) |
| 404 | Resource missing **or** owned by another user (`not_found`) |
| 409 | Conflict — duplicate email, report for an unfinished analysis |
| 413 | Upload exceeds `MAX_UPLOAD_MB` (`file_too_large`) |
| 415 | Unsupported/invalid container (`unsupported_format`, `invalid_audio`, `empty_file`) |
| 422 | Schema/validation failure (`validation_error`) |
| 429 | Rate limited (`rate_limited`) |
| 503 | AI model unavailable (`model_unavailable`) |

## Authentication

Tokens are JWT bearer tokens (`HS256`, issuer `voiceguard-ai`). Send
`Authorization: Bearer <access_token>`.

### POST `/auth/register`

```json
{ "name": "Ada Lovelace", "email": "ada@example.com", "password": "Str0ngPass123" }
```

Rules: name 2–120 chars, valid email (stored lowercase), password 8–72 chars with a letter and a digit.
`201` → `{ "access_token", "token_type": "bearer", "expires_in", "user": {…} }` · `409` if the email exists.

### POST `/auth/login`

```json
{ "email": "ada@example.com", "password": "Str0ngPass123" }
```

`200` with the same token envelope · `401` `Invalid email or password.` (identical message for unknown email).

### GET `/auth/me` → `UserOut`

```json
{ "id": 1, "name": "Ada Lovelace", "email": "ada@example.com",
  "preferences": { "email_notifications": false, "default_view": "dashboard" },
  "created_at": "2026-11-18T09:12:04.512Z" }
```

### PATCH `/auth/me`

```json
{ "name": "Ada L.", "preferences": { "default_view": "history", "compact_tables": true } }
```

Only `email_notifications`, `default_view`, `compact_tables`, `theme` are persisted.

### POST `/auth/change-password`

```json
{ "current_password": "Str0ngPass123", "new_password": "N3wStrongPass" }
```

`200` → `{ "message": "Password updated successfully." }` · `401` wrong current password.

## Audio

### POST `/audio/upload` (multipart)

Field `file` — `.wav` or `.mp3`, ≤ 20 MB, 1–60 s. The container header is checked against the extension;
the filename is sanitised and the file is stored under a random UUID.

`201` → pending analysis:

```json
{ "id": 42, "filename": "interview.wav", "source": "upload",
  "audio_duration": 4.2, "sample_rate": 16000, "channels": 1,
  "file_format": "wav", "file_size_bytes": 134584,
  "predicted_class": null, "model_score": null, "model_version": null,
  "analysis_status": "pending", "failure_reason": null,
  "analysis_duration_ms": null, "audio_features": null, "model_details": null,
  "created_at": "2026-11-18T09:20:11.020Z" }
```

`stored_file_reference` is never returned.

### POST `/audio/analyze`

```json
{ "analysis_id": 42 }
```

Runs inference (returns the existing result if already `completed`). Possible statuses:

| `analysis_status` | Meaning |
| --- | --- |
| `completed` | `predicted_class` is `genuine`/`synthetic`, `model_score` in [0,1] |
| `unavailable` | Model could not be loaded; `failure_reason` explains it |
| `failed` | Audio could not be processed; `failure_reason` explains it |
| `pending` | Not analysed yet |

Completed payload additionally includes `audio_features` (descriptive signal metrics) and
`model_details` (labels, per-window scores, threshold, aggregation, inference time).

### GET `/audio/{id}` · DELETE `/audio/{id}`

`GET` returns `AnalysisOut`. `DELETE` removes the row (cascading reports) and the stored audio file:

```json
{ "message": "Analysis deleted.", "id": 42 }
```

### GET `/audio/{id}/waveform?buckets=800`

```json
{ "peaks": [0.0, 0.12, 0.94, …], "duration": 4.2, "sample_rate": 4000 }
```

### GET `/audio/{id}/spectrogram` → `image/png`

Log-mel spectrogram (96 bands, 0–8 kHz), rendered server-side with Pillow. `Cache-Control: private, max-age=300`.

### POST `/audio/compare` (multipart)

Fields `file_a`, `file_b`. Both are validated and analysed independently.

```json
{ "left": { …AnalysisOut… }, "right": { …AnalysisOut… },
  "duration_delta_seconds": 1.0, "score_delta": 0.04,
  "disclaimer": "AI voice detection is not 100% reliable. …" }
```

### GET `/audio/limits/info`

```json
{ "max_upload_mb": 20, "allowed_formats": ["mp3", "wav"],
  "min_duration_seconds": 1.0, "max_duration_seconds": 60.0 }
```

## Forensics

### GET `/forensics/{analysis_id}` → `ForensicsOut`

Bearer token required; only the owner can read a record (another user's id returns 404).

Returns everything the forensics workspace renders for the stored file:

| Group | Fields |
| --- | --- |
| `audio` | `duration_seconds`, `analysed_seconds`, `sample_rate_hz`, `channels`, `frames`, `container`, `subtype`, `file_size_bytes`, `nyquist_hz`, `channel_layout`, `truncated_for_analysis` |
| `waveform` | `peaks` (600 buckets), `buckets`, `duration` |
| `signal` | `rms_timeline` (≤160 points with timestamps), `band_energy` (six bands with relative `share`), `spectral_centroid_hz`, `spectral_rolloff_hz`, `zero_crossing_rate`, `peak_amplitude`, `silence_ratio`, `note` |
| `model` | Stored model output only: `status`, `predicted_class`, `model_score`, `model_version`, `threshold`, `windows_analyzed`, `window_seconds`, `window_scores`, `aggregation`, `inference_ms`, `parameters`, `device`, `failure_reason` |

Signal analysis is capped at 30 s; `truncated_for_analysis` is `true` when the recording is longer.
Charts are measurements of the uploaded signal, not verified forensic evidence. Errors: 401
unauthenticated, 404 not owned/missing, 410 stored file gone, 422 undecodable audio.

### GET `/forensics/{analysis_id}/media`

Streams the stored recording for playback (`audio/wav` or `audio/mpeg`, `Content-Disposition: inline`,
`Cache-Control: private, no-store`). Same authentication and ownership rules as above.

## History

### GET `/history`

Query parameters: `q` (filename contains), `status` (`pending|completed|unavailable|failed`),
`prediction` (`genuine|synthetic`), `sort` (`created_at|filename|model_score|audio_duration`),
`order` (`asc|desc`), `page` ≥ 1, `page_size` 1–50.

```json
{ "items": [ …AnalysisOut… ], "total": 12, "page": 1, "page_size": 10, "pages": 2 }
```

Ordering is stabilised with an id tiebreaker so pagination cannot repeat or skip rows.

### GET `/history/{id}` → `AnalysisOut`

## Reports

### GET `/reports/{analysis_id}/download`

`200` → `application/pdf` with
`Content-Disposition: attachment; filename="voiceguard-report-VG-XXXXXXXXXX.pdf"`, `Cache-Control: private, no-store`.
The report row (unique `report_reference`) is created on first download and reused afterwards.
`409` if the analysis is not `completed`.

Report contents: branding, report ID, analysis ID, account email, filename, format/duration/sample
rate/channels/size/source, verdict, model score, model version, threshold, windows analysed, aggregation,
raw window scores, processing time, descriptive features, and the limitations disclaimer.

### GET `/reports/{analysis_id}/metadata`

```json
{ "report_reference": "VG-3F9C21AB77", "analysis_id": 42 }
```

## Analytics

### GET `/analytics/summary`

```json
{ "total_analyses": 12, "genuine": 8, "synthetic": 3, "unavailable": 1,
  "pending": 0, "failed": 0, "average_confidence": 0.2143,
  "average_duration": 4.21, "total_audio_seconds": 50.5,
  "last_analysis_at": "…", "last_successful_at": "…", "first_analysis_at": "…" }
```

### GET `/analytics/trends?days=14` (7–90)

```json
{ "range_days": 14,
  "daily": [ { "date": "2026-11-05", "total": 2, "genuine": 1, "synthetic": 1, "other": 0 } ],
  "confidence_buckets": [ { "label": "0-20%", "count": 5 } ],
  "duration_buckets": [ { "label": "< 5 s", "count": 4 } ],
  "status_breakdown": [ { "label": "completed", "count": 11 } ] }
```

## System

### GET `/health`

Public. If a valid bearer token is supplied, `last_successful_analysis_at` is included for that user.

```json
{ "status": "operational", "app": "VoiceGuard AI", "version": "1.0.0",
  "environment": "development", "database": "connected", "model_available": false,
  "uptime_seconds": 812, "timestamp": "…", "last_successful_analysis_at": null }
```

### GET `/model/status?load=true`

```json
{ "available": true, "loaded": true,
  "model_id": "Vansh180/deepfake-audio-wav2vec2",
  "model_version": "Vansh180/deepfake-audio-wav2vec2@e1197e2063",
  "device": "cpu", "sample_rate": 16000, "labels": { "0": "real", "1": "fake" },
  "window_seconds": 4.0, "max_windows": 3, "threshold": 0.5,
  "parameters": 94569090, "detail": null }
```

Without `load=true` the endpoint reports current state only (no download/inference is triggered).

## Forensics — segments (Phase 2)

### GET `/forensics/{analysis_id}/segments`

Stored window-by-window result. Returns `200` with `computed: false`, `segments: []`
and `aggregate: null` before anything is computed. `401` anonymous · `404` missing
or foreign analysis.

```json
{ "analysis_id": 42, "computed": true, "cached": false, "computed_at": "…",
  "window_seconds": 2.0, "hop_seconds": 1.0, "overlap_ratio": 0.5,
  "sample_rate": 16000, "total_duration": 6.8683, "total_segments": 6,
  "model_id": "Vansh180/deepfake-audio-wav2vec2",
  "model_version": "Vansh180/deepfake-audio-wav2vec2@e1197e2063",
  "segments": [ { "index": 0, "start_seconds": 0.0, "end_seconds": 2.0,
                  "duration_seconds": 2.0, "state": "done", "label": "genuine",
                  "score": 0.48975, "reason": null, "model_version": "…" } ],
  "aggregate": { "method": "duration-weighted mean over completed segments",
                 "score": 0.193688, "label": "genuine", "scored_label": "genuine",
                 "scope": "whole_file", "reliability_note": null, "threshold": 0.5,
                 "completed_segments": 6, "unsupported_segments": 0, "error_segments": 0,
                 "excluded_segments": 0, "coverage_seconds": 6.868,
                 "coverage_ratio": 1.0, "whole_file_reliable": true,
                 "whole_file_score": 0.06836 },
  "caveat": "Each segment score is the model output for that window only. …" }
```

`state` is `done`, `unsupported` (short/silent segment, no score) or `error`
(inference failed for that segment only); `label`/`score` are `null` unless `done`.

#### Aggregate scope, `whole_file_reliable` and partial results

`aggregate` describes **only the segments that were scored**. Its fields:

| field | meaning |
| --- | --- |
| `method` | how the aggregate score is built: duration-weighted mean over completed segments |
| `score` | Σ(segment score × segment duration) ÷ Σ(segment duration) over `done` segments; `null` if none was scored |
| `scored_label` | label of that aggregate score (`genuine`/`synthetic`) — **about the scored segments only** |
| `label` | whole-file verdict. `null` unless `whole_file_reliable` is `true` |
| `scope` | `whole_file` when `whole_file_reliable` is `true`, otherwise `partial` |
| `reliability_note` | why the result is partial (e.g. coverage below threshold, excluded segments); `null` when reliable |
| `completed_segments` / `unsupported_segments` / `error_segments` | counts per state |
| `excluded_segments` | `unsupported_segments + error_segments`; these rows carry no score and never contribute to `score`/coverage |
| `coverage_seconds` | union of the completed segments' time ranges (overlaps are not double counted) |
| `coverage_ratio` | `coverage_seconds ÷ total_duration`, clamped to `1.0` |
| `whole_file_reliable` | **coverage/completeness only** — `true` only when `coverage_ratio >= 0.95` **and** there are no excluded segments **and** at least one score exists. It says nothing about prediction accuracy or authenticity |
| `whole_file_score` | the stored whole-file model score, repeated for comparison; never overwritten by the segment run |

`coverage_ratio >= 0.95` is the fixed threshold (`RELIABLE_COVERAGE_RATIO`). A
recording where a whole-file verdict is not supportable therefore looks like:

```json
{ "score": 0.82, "scored_label": "synthetic", "label": null,
  "scope": "partial",
  "reliability_note": "Coverage 50.0% is below the 95% threshold; 2 segment(s) were excluded (2 unsupported, 0 error). The score and scored_label describe the scored segments only, not the whole file.",
  "completed_segments": 2, "unsupported_segments": 2, "error_segments": 0,
  "excluded_segments": 2, "coverage_seconds": 2.0, "coverage_ratio": 0.5,
  "whole_file_reliable": false }
```

Important: an aggregate `score` (and `scored_label`) **can exist even when
coverage is insufficient** — one scored second of a 60 s file still yields a
score with `coverage_ratio: 0.0167`. Such a result is explicitly `scope:
"partial"` with `label: null`; clients must not present it as a whole-file
verdict. Per-segment `label`/`score` values remain available and unchanged.

### POST `/forensics/{analysis_id}/segments?window_seconds=2&hop_seconds=1&force=false`

Scores every planned window and stores it. `window_seconds`/`hop_seconds` are
optional (`0 < value <= 30`); `force=true` recomputes and replaces the rows.
Idempotent — a repeat call without `force` returns the stored rows with
`cached: true` and runs no inference. `409` if the model is unavailable (nothing
is stored) · `410` if the audio file was removed · `422` for an invalid plan or
more than 60 segments. See `docs/PHASE_2_SEGMENTS.md`.

## Forensics - signal quality (Phase 3)

`GET /forensics/{analysis_id}` now also contains a `quality` block measured from
the decoded signal (mono, 16 kHz, first 30 s):

```json
"quality": {
  "peak_dbfs": -6.02, "rms_dbfs": -9.03, "crest_factor_db": 3.01,
  "dynamic_range_db": 4.2, "clipping_ratio": 0.0, "dc_offset": 0.0001,
  "snr_estimate_db": 31.4, "effective_bandwidth_hz": 7600.0,
  "spectral_flatness": 0.012, "silence_ratio": 0.08,
  "leading_silence_seconds": 0.0, "trailing_silence_seconds": 0.0,
  "longest_silence_seconds": 0.03, "analysed_seconds": 3.0,
  "nyquist_hz": 8000.0,
  "observations": [
    { "code": "clean", "severity": "info",
      "title": "No strong quality problems measured", "detail": "…" }
  ],
  "note": "These are measurements of the decoded signal … not evidence of authenticity."
}
```

`observations[].severity` is `info`, `caution` or `warning`; each observation
explains the measured condition. Quality values are descriptive only and never
affect a model score. `audio.bit_depth` and `audio.average_bitrate_kbps` were
also added to the metadata block.

### GET `/forensics/{analysis_id}/segment-signal`

Signal measurements per stored segment (or the default 4 s / 2 s plan when no
segments are stored): `index`, `start_seconds`, `end_seconds`,
`duration_seconds`, `state`, `rms_dbfs`, `peak_dbfs`, `silence_ratio`,
`clipping_ratio`, `spectral_centroid_hz`, plus the same `quality` block and a
`note`. The file is decoded once for all windows. `computed` is `false` when the
dash shows a plan rather than stored segments. `422` for silent/unreadable audio,
`410` when the file is gone, `404` for another user's record.

## Live (near-real-time) analysis (Phase 4)

Chunked analysis with the real detector. Every response states
`mode: "near_real_time_chunked"`, a `latency_note` (latency ≥ chunk length +
inference; not continuous monitoring) and a `caveat` (the running average is not
a whole-file verdict). Chunk audio is deleted after scoring and nothing is
written to the database.

| method | path | notes |
| --- | --- | --- |
| POST | `/stream/sessions` | `{ "chunk_seconds": 3 }` (0.5–10); max 3 active per user (`429`) |
| POST | `/stream/sessions/{id}/chunks` | multipart `file` + optional `chunk_index`; out-of-order → `409` |
| GET | `/stream/sessions/{id}` | current state and per-chunk results |
| POST | `/stream/sessions/{id}/stop` | closes the session, returns the summary |
| DELETE | `/stream/sessions/{id}` | discards it immediately |

Chunk errors: `415` invalid container, `422` silent / too short / too long,
`503` model unavailable, `409` closed or over the 40-chunk limit. Live sessions
expire after 10 minutes of inactivity.

## Report contents (Phase 7)

The PDF from `GET /reports/{analysis_id}/download` includes the stored model
result, window-by-window table with coverage and a **Partial - not a whole-file
conclusion** scope line when `whole_file_reliable` is false, recording-quality
observations when the audio is still present, and the limitations/disclaimer
section. Reports exist only for completed analyses (`409` otherwise).

## Rate limits

| Scope | Default |
| --- | --- |
| `/auth/*` mutations | 10 requests / 60 s per client IP |
| `/audio/upload`, `/audio/analyze`, `/audio/compare`, `/forensics/*/segments`, `/forensics/*/segment-signal`, `/reports/*/download`, `/stream/*` | 20 requests / 60 s per user |

Exceeding a limit returns `429` with a retry hint in `detail`.
