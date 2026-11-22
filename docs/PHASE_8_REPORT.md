# Phase 8 - Security and data management

Status: **hardened and tested**. Existing authentication, ownership rules and storage layout
were preserved.

## Audit findings (already in place)

* Passwords hashed with bcrypt, per-password salt; never logged or returned.
* JWT bearer tokens signed with a server-side key (env or persisted random key), expiry 12 h.
* Every analysis query goes through `get_owned_analysis`, which returns the **same 404** for
  "missing" and "someone else's" — no record enumeration.
* Uploads: extension whitelist, magic-header check, extension/content match, 20 MB cap,
  duration/sample-rate/channel bounds, random UUID storage names outside the web root,
  `.part` cleanup on failure and stale-file purge at startup.
* CORS restricted to configured origins plus localhost dev ports; credentials allowed.
* Central error handlers never return stack traces or internal messages.
* Rate limiting already covered auth, upload, analyse and compare.

## Added in this phase

### 1. Security headers (`app/main.py`)

| header | value |
| --- | --- |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `no-referrer` |
| `Cross-Origin-Opener-Policy` | `same-origin` |
| `X-Permitted-Cross-Domain-Policies` | `none` |
| `Permissions-Policy` | `camera=(), geolocation=(), microphone=(self)` |
| `Cache-Control` (API paths) | `no-store` |

### 2. Rate limiting on the new/expensive routes

`POST /api/forensics/{id}/segments`, `GET /api/forensics/{id}/segment-signal` and
`GET /api/reports/{id}/download` now use the shared per-user analysis budget, matching the
existing upload/analyse limits. Live sessions were already limited per chunk.

### 3. Input validation on the new surfaces

* Live chunks: extension + magic header, 8 MB cap, 0.5 s minimum, session chunk length + 1 s
  maximum, silent/invalid sample rejection, ordered indices.
* Segment plan: window 0.5–30 s, hop ≤ window, ≤ 60 segments, duplicate-safe upsert.
* Report/segment-signal: missing media → `410`, non-completed analysis → `409`.

## Data retention and privacy (implemented behaviour)

| data | lifetime |
| --- | --- |
| Uploaded audio | `storage/audio/<user_id>/<uuid>.<ext>` until the analysis is deleted |
| Analysis + segments + reports rows | PostgreSQL, cascade-deleted with the analysis or user |
| Temporary upload parts | deleted on failure; stale `*.part` purged at startup (> 1 h) |
| Live-chunk audio | temp file only, unlinked in `finally` immediately after scoring |
| Live session results | process memory, 10-minute TTL / explicit discard; never in the DB |
| JWT signing key | `SECRET_KEY` env var, else `storage/.jwt_secret` (not committed) |
| PDF reports | generated on demand, not written to disk |

Deletion control: `DELETE /api/audio/{id}` removes the DB rows (cascade) and the stored file.
There is no bulk "delete all data" endpoint; an account can be cleared by deleting each
analysis (documented rather than inventing a destructive endpoint).

## Tests

`backend/tests/test_security.py` - 6 tests: header contract, extension rejection, content/
extension mismatch, 429 on the segment endpoint, non-leaking 401, and indistinguishable
404s for missing vs foreign records. Existing auth/upload/ownership suites also pass.

## Known limitations

* The limiter is in-process, so limits are per worker; use Redis (or a single worker) when
  scaling horizontally.
* No CSRF concern for the API itself (bearer tokens, no cookies), but the frontend stores the
  JWT in `localStorage`; an XSS would expose it. No CSP is set because the bundled docs UI
  uses inline scripts.
* No server-side antivirus scan; audio is parsed by libsndfile/librosa and never executed.
* No account-level bulk deletion endpoint (per-record deletion only).
* HTTPS is terminated by the operator's proxy; the app does not set HSTS.
