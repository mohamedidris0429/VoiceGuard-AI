# Phase 7 - Report generation

Status: **implemented and tested** (PDF built from stored records only).

## Report contents

`GET /api/reports/{analysis_id}/download` now renders:

1. Header, report reference, analysis id, account e-mail, generation time.
2. **Result** block: verdict text, model score, threshold context.
3. **Recording**: filename, format, duration, sample rate, channels, size, source, analysed-at.
4. **Model and processing**: model id/version, task, threshold, windows analysed/length,
   aggregation, raw window scores, processing time, status.
5. **Window-by-window analysis** (new): windows scored/total, coverage % with seconds,
   excluded windows, aggregate score, scope (`Whole file` or
   `Partial - not a whole-file conclusion`), aggregate label (only when reliable) and the
   stored whole-file model score for comparison. A partial aggregate prints an explicit
   warning plus `reliability_note`, then a table of up to 40 windows
   (window, state, score, model label) and the "independent probabilistic outputs" caveat.
6. **Recording-quality observations** (new, optional): peak/RMS/crest/SNR/bandwidth,
   clipping %, DC offset, silence ratio, and each Phase 3 observation with its explanation.
   Measured from the stored file at download time; omitted cleanly if the file is gone.
7. **Descriptive signal features** (existing) with the "not used by the model" note.
8. **Limitations and disclaimer**, plus the standard footer on every page.

No value is invented: unavailable data prints "Not available", and non-completed analyses
cannot produce a report (`409`).

## Authorization and failure handling

* Report is only produced for an analysis owned by the caller (`404` otherwise, identical to
  "missing"), and only when `analysis_status == "completed"` (`409`).
* Report references are persisted once per analysis (`VG-XXXXXXXXXX`), so repeated downloads
  are stable.
* Missing stored audio does not break the report — the quality section is simply omitted.
* Downloads send `Content-Disposition: attachment`, `Cache-Control: private, no-store` and
  an exact `Content-Length`.
* The route is rate-limited with the shared analysis budget.

## Tests

`backend/tests/test_reports_phase7.py` - 3 tests:

* a partial segment analysis produces a PDF whose extracted text contains
  "Window-by-window analysis", "Partial", "Coverage", "not a whole-file conclusion",
  "Recording-quality observations" and the disclaimer;
* a report still downloads when the media file has been deleted, without the quality section;
* another user receives `404`.

The helper extracts text from ReportLab's ASCII85+Flate streams (base64 + zlib), so the
assertions check actual rendered content rather than the raw PDF container.

## Limitations

* Reports are generated synchronously; typical size is a few tens of KB.
* Window tables are capped at 40 rows per report (noted in the document when truncated).
* Quality observations depend on the original file still being present.
* Only PDF is offered (no DOCX/CSV export).
