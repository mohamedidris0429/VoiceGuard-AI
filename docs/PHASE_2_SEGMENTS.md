# Phase 2 — Audio segment-level analysis

Phase 2 scores a recording **segment by segment** with the same pretrained
detector used for the whole-file verdict. It adds storage, one service and two
endpoints. Phase 1 endpoints, auth, models and the frontend are unchanged.

## Pipeline

1. Decode the stored file to mono float32 at the model sample rate (16 kHz) and
   re-check the configured duration limits.
2. Plan overlapping segments:

   ```python
   plan_segments(duration_s, window=4.0, hop=2.0, min_duration=1.0)
   ```

   - `window` is clamped to `0.5 … 30 s`, `hop` to `0.1 … window`;
   - segments start at `0, hop, 2·hop, …` and the **final segment is clamped to
     the real audio duration** (it never extends past the end of the file);
   - a segment shorter than `min_duration` — typically the clamped tail — is
     planned with state `unsupported` and is **never** sent to the detector;
   - more than 60 segments is rejected (`422`) so one request cannot fan out
     without bound.
3. Score each supported segment independently:
   `get_detector().predict(chunk, sample_rate)` — the existing real detector, no
   second model, no fallback, no random values.
4. Persist one row per segment with an explicit state:
   - `done` — the detector returned a score;
   - `unsupported` — too short, empty, or silent (`score`/`label` are `NULL`,
     `reason` explains why);
   - `error` — inference for this segment failed (`score`/`label` `NULL`).
5. Aggregate the completed segments only and store the plan + aggregate in
   `audio_analyses.segment_meta` for audit.

If the model cannot be loaded, the request fails with `409 model_unavailable`
and **nothing is persisted**.

## Storage

`analysis_segments` (migration `0002_segments`):

| column | notes |
| --- | --- |
| `id` | primary key |
| `analysis_id` | FK → `audio_analyses.id`, `ON DELETE CASCADE`, indexed |
| `segment_index` | unique together with `analysis_id` |
| `start_seconds`, `end_seconds` | segment bounds in seconds |
| `state` | `done` / `unsupported` / `error` |
| `label`, `score` | model output for that segment (`NULL` unless `done`) |
| `reason` | why a segment was not scored |
| `model_name`, `model_version` | checkpoint used |
| `created_at` | UTC timestamp |

Constraints/indexes: `uq_analysis_segments_analysis_index (analysis_id,
segment_index)`, `ix_analysis_segments_analysis_id`,
`ix_analysis_segments_analysis_order (analysis_id, segment_index)`.

`audio_analyses.segment_meta` (nullable JSON) holds the audit record: window,
hop, overlap, sample rate, total duration, total segments, model id/version,
aggregate and the caveat text. Nullable and additive, so existing rows and
Phase 1 responses are unaffected.

## Endpoints

### `GET /api/forensics/{analysis_id}/segments`

Returns the stored result. Before anything is computed: `200` with
`computed: false`, `segments: []`, `aggregate: null`. `404` still means the
analysis is missing or belongs to another user.

### `POST /api/forensics/{analysis_id}/segments`

Query parameters: `window_seconds` (`0 < w ≤ 30`, default 4.0), `hop_seconds`
(`0 < h ≤ 30`, default 2.0), `force` (default `false`).

Idempotent: a repeat call without `force` returns the stored rows with
`cached: true` and runs no inference. `force=true` replaces them in a single
transaction (unique constraint + delete-then-insert), so no duplicate rows exist.

Status codes: `401` anonymous · `404` missing/foreign analysis · `409` model
unavailable (nothing stored) · `410` audio file removed · `422` invalid plan,
invalid duration, or > 60 segments.

## Honest aggregation

```json
{
  "method": "duration-weighted mean over completed segments",
  "score": 0.193688,
  "label": "genuine",
  "scored_label": "genuine",
  "scope": "whole_file",
  "reliability_note": null,
  "threshold": 0.5,
  "completed_segments": 6,
  "unsupported_segments": 0,
  "error_segments": 0,
  "excluded_segments": 0,
  "coverage_seconds": 6.868,
  "coverage_ratio": 1.0,
  "whole_file_reliable": true,
  "whole_file_score": 0.06836
}
```

- `score` = Σ(score × segment duration) / Σ(segment duration) over `done` rows.
- `coverage_ratio` = union of the completed segments ÷ file duration (overlaps
  are not double counted), so a partial result is visible rather than implied.
- `whole_file_reliable` is `true` only at ≥ 95 % coverage (`RELIABLE_COVERAGE_RATIO`)
  with no excluded rows and at least one score. It measures **coverage only** —
  never prediction accuracy or authenticity.
- `whole_file_score` repeats the stored whole-file score for comparison; the
  segment run never overwrites it.

### Partial results are scoped, not presented as a verdict

A low-coverage aggregate keeps its diagnostic numbers but loses the whole-file
verdict:

| field | reliable aggregate | partial aggregate |
| --- | --- | --- |
| `whole_file_reliable` | `true` | `false` |
| `scope` | `whole_file` | `partial` |
| `label` | `genuine` / `synthetic` | `null` |
| `scored_label` | label of the scored segments | label of the scored segments (kept) |
| `score` | duration-weighted score | same score, but scoped to the scored segments |
| `reliability_note` | `null` | why it is partial (coverage %, excluded count) |

`label` is the only whole-file claim in the response and it is `null` whenever
the coverage is insufficient. The rule is enforced twice: when the aggregate is
built (`segment_service.aggregate_segments`) and again by a Pydantic
`model_validator` on `SegmentAggregateOut`, so a stored aggregate written by an
older build cannot resurface a partial result as a whole-file verdict. Segment
rows, their scores, labels, states and reasons are unchanged.

This is the backward-compatible choice: no column is removed, no segment data is
lost, and `score`/per-segment fields keep their meaning. Only `label` becomes
`null` where it previously (incorrectly) looked like a whole-file verdict.
`scored_label` is the additive replacement for that diagnostic value; stored
aggregates from before this change are normalised on read (their `scored_label`
is derived from the old `label`).

## Caveats (returned as `caveat`)

> Segment scores are probabilistic model outputs for individual windows, not
> proof of authenticity. A low score in one segment does not prove that audio is
> genuine, and a high score does not prove it is cloned. The aggregate covers
> only the completed segments — compare it with `coverage_ratio` before treating
> it as a whole-file result. When coverage is insufficient or segments were
> excluded, the whole-file label is null and the result is scoped as partial.

Also worth knowing:

- The detector always feeds a fixed 4 s tensor; segments shorter than
  `MODEL_WINDOW_SECONDS` are zero-padded by the existing windowing code, so a
  1–2 s segment score is not a pure short-window measurement.
- Boundaries follow the hop, not speech activity: a segment can straddle a pause
  or a speaker change.

## Configuration

| setting | default | meaning |
| --- | --- | --- |
| `SEGMENT_WINDOW_SECONDS` | `4.0` | default window length |
| `SEGMENT_HOP_SECONDS` | `2.0` | default hop |
| `SYNTHETIC_THRESHOLD` | `0.5` | label threshold (shared with Phase 1) |
| `MODEL_SAMPLE_RATE` | `16000` | decode rate (shared with Phase 1) |

Test coverage: `backend/tests/test_segments.py` (28 tests) covers planning and
overlap, clamped short tails, persistence, aggregation and coverage,
unsupported/error handling, idempotency, auth/ownership, missing media, model
unavailability, and the partial-vs-whole-file response contract (no `label`
without `whole_file_reliable`, `scored_label` preserved, `reliability_note`
explains the reason).
