# Phase 4 - Near-real-time audio analysis

Status: **implemented and tested** (backend fully; browser microphone flow built, not
exercised on hardware in this environment).

## Design

The browser records **self-contained clips** (default 3 s) one after another and uploads
each one as it is finalised. The server scores the chunk with the same pretrained detector
used for whole-file analysis and returns the running session immediately.

```
Browser MediaRecorder ──3 s clip──► decodeAudioData ──► 16-bit mono WAV
        │                                                   │
        └──────── next clip (sequential, no overlap) ───────┤
                                                            ▼
                     POST /api/stream/sessions/{id}/chunks (FormData)
                                    │
                       decode 16 kHz mono ─► detector.predict()
                                    │
                        chunk result + running average (in memory)
```

### Why chunked HTTP rather than one continuous stream

* The existing detector expects a bounded waveform; chunking keeps RAM flat (one chunk is
  ~96 KB decode at 16 kHz for 3 s).
* No WebSocket server, no extra runtime dependency, works through ordinary HTTP and the
  existing JWT auth.
* Every chunk is a complete, independently decodable file, so an interrupted connection or
  a browser restart cannot corrupt the session.

### Honesty contract

Every API response contains:

* `mode: "near_real_time_chunked"`;
* `latency_note`: latency is at least the chunk length plus inference, with a gap between
  chunks — **not continuous or instantaneous detection**;
* `caveat`: chunk scores are independent model outputs; the running average is not a
  whole-file verdict and is never stored as one;
* `window_note`: the detector pads short chunks to its 4 s window and averages up to 3 windows.

The UI repeats the same statements and labels the page "Near-real-time voice monitor".

## Endpoints (`/api/stream`)

| method | path | purpose |
| --- | --- | --- |
| POST | `/sessions` | create a session (`chunk_seconds` 0.5–10, default 3) |
| POST | `/sessions/{id}/chunks` | score one chunk; optional `chunk_index` enforces order |
| GET | `/sessions/{id}` | current state |
| POST | `/sessions/{id}/stop` | close and return the summary |
| DELETE | `/sessions/{id}` | discard immediately |

## Bounded memory and privacy

* Sessions live in a process-local registry: max 3 active per user, 40 chunks per session,
  10-minute TTL, purged on access.
* Chunk audio is written to `storage/tmp` only for decoding and is deleted in a `finally`
  block — no recording is retained.
* Nothing is written to PostgreSQL; live results disappear when the session is discarded or
  expires. Tests assert both behaviours (`test_chunk_is_scored_and_audio_is_not_retained`).
* Chunk size is capped (8 MB) and content is header-checked before decoding.

## Failure handling

| condition | behaviour |
| --- | --- |
| microphone permission denied / no device | UI messages, session discarded |
| recorder error or empty blob | UI error, loop stops, session closed |
| network failure on a chunk | UI shows the error, stops the loop, closes the session |
| out-of-order chunk | `409 chunk_out_of_order` |
| chunk too long / too short | `422` with the measured duration |
| silent chunk | `422` "nothing for the model to score" |
| stopped session | `409 stream_session_closed` |
| model unavailable | `503`, nothing appended |
| page unload | tracks stopped, recorder stopped, session discarded (best effort) |

## Tests

`backend/tests/test_stream.py` - 14 tests: auth, session contract/caveat, chunk bounds,
scoring and audio deletion, DB-untouched assertion, ordering, running average, stop
rejection, per-user isolation, unknown session, session cap (429), oversize/silent/corrupt
chunks, discard.

## Limitations

* Latency is inherently ≥ one chunk (3 s default) plus CPU inference; this is documented
  rather than hidden.
* There is a short gap between clips while the browser finalises and uploads each one.
* No cross-process state: sessions are per-process, so a multi-worker deployment needs
  sticky sessions (documented in the deployment guide).
* The microphone/session flow was **not** tested with real browser hardware in this
  environment; only the API contract and logic were tested. The build passes.
