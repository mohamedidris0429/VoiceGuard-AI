# Phase 11 - Performance and deployment readiness

Status: **reviewed and documented; no deployment was performed.**

## Resource review (measured where possible)

| resource | observation |
| --- | --- |
| Model on disk | ~378 MB wav2vec 2.0 checkpoint in `.cache/huggingface` |
| Model in RAM | single lazy singleton; ~94.6 M parameters in float32 (~380 MB) plus PyTorch overhead — this is the dominant memory cost |
| Audio decode | 60 s mono @16 kHz float32 ≈ 3.8 MB; forensic/quality work is capped at 30 s |
| Chunk audio | 3 s @16 kHz ≈ 96 KB decoded; temp file deleted immediately |
| Windows per request | whole-file: ≤ 3 × 4 s; segments: ≤ 60 sequential windows |
| Frontend bundle | 753 KB JS (209 KB gzip) + 29 KB CSS; single chunk, pre-existing size warning |
| DB | 4 tables; indexes on `(user_id, created_at)`, `(user_id, status)`, `(user_id, class)`, `analysis_id` |

No optimisation is claimed as a speed-up because no before/after benchmark was run. Bounded
work is enforced by configuration rather than measurement:

* `model_max_windows = 3`, segment cap 60, forensics cap 30 s, upload cap 20 MB / 60 s.
* `torch.set_num_threads(min(4, cpu_count))` (configurable via `MODEL_THREADS`).
* Live sessions capped at 40 chunks and 10-minute TTL.
* Rate limits protect CPU-bound endpoints.

### Database queries

* History uses SQL `COUNT` + sorted/offset page with an id tiebreaker; filters are indexed
  columns or a leading-wildcard `lower(filename)` scan limited by `page_size ≤ 50`.
* Analytics aggregates are single `SELECT`s over `user_id`-filtered rows.
* Segment upsert runs in one transaction; no N+1 queries in list endpoints (relationship
  loading is only used for a single analysis in reports).

### Model loading and lifecycle

* Lazy load on first analysis; `/api/model/status?load=true` preloads.
* Thread-safe singleton with a 120 s retry cooldown after a failed load.
* Startup purges stale `.part` uploads and logs configuration; shutdown is logged. No
  background threads or model unload — an idle process keeps the ~380 MB model resident once
  loaded. Set `MODEL_OFFLINE=1` for air-gapped cache-only operation.

## Deployment artefacts

* `docs/DEPLOYMENT_GUIDE.md` — full install, configuration, migration, proxy, backup,
  upgrade, rollback and troubleshooting steps.
* Health endpoints: `GET /api/health` (API + DB + uptime), `GET /api/model/status`.
* Operational logging: `voiceguard`, `voiceguard.analysis`, `voiceguard.ai`,
  `voiceguard.segments`, `voiceguard.errors`; unhandled exceptions are logged with context and
  returned as a generic 500.

## Production configuration checklist

* `SECRET_KEY` set from the environment (do not rely on the generated file in production).
* `DATABASE_URL` with a least-privilege role; `ENVIRONMENT=production`.
* `CORS_ORIGINS` restricted to the real frontend origin(s); no wildcard.
* `MODEL_CACHE_DIR` on persistent disk; pre-download weights and set `MODEL_OFFLINE=1` if the
  host has no outbound network.
* Run a **single** uvicorn worker (in-process rate limiter and live-session registry).
* Put TLS in front; set `client_max_body_size ≥ 20m` and generous read timeouts.

## What still requires a human

* Supplying PostgreSQL credentials and TLS certificates.
* Downloading the model once (~378 MB) or copying the cache.
* Choosing and provisioning the host, and running the service manager commands.
* Running an evaluation on a labelled dataset if accuracy claims are needed.

No paid service was provisioned and nothing was deployed.
