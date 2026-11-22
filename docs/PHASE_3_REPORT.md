# Phase 3 - Advanced forensic enhancements

Status: **implemented and tested**. Phase 1 and Phase 2 endpoints and schema are unchanged.

## What was added

### 1. Signal-quality measurements (`app/services/forensic_service.py`)

Computed from the decoded signal (mono, 16 kHz, first 30 s) with numpy/librosa only:

| measurement | method |
| --- | --- |
| `peak_dbfs`, `rms_dbfs` | 20·log10 of peak / RMS amplitude, floored at −180 dBFS |
| `crest_factor_db` | peak dBFS − RMS dBFS |
| `dynamic_range_db` | 95th − 5th percentile of frame RMS (dB) |
| `clipping_ratio` | fraction of samples at ≥ 0.999 full scale |
| `dc_offset` | mean sample value |
| `snr_estimate_db` | 90th percentile frame level − 10th percentile frame level |
| `effective_bandwidth_hz` | frequency below which 99 % of the mean STFT magnitude lies |
| `spectral_flatness` | mean librosa spectral flatness |
| `silence_ratio`, `leading/trailing/longest_silence_seconds` | frame RMS below 25 % of the mean frame RMS |

Each report includes `observations`: `{code, severity, title, detail}` with plain-language
explanations (clipping, DC offset, low SNR, band-limited audio, mostly silent, compressed
dynamics, digital silence, or "no strong quality problems"). Severity is one of `info`,
`caution`, `warning`.

### 2. Richer metadata

`GET /api/forensics/{id}.audio` now also reports `bit_depth` (from the libsndfile subtype)
and `average_bitrate_kbps` (container size × 8 ÷ duration — for WAV this is the uncompressed
rate, for MP3 the average stream rate).

### 3. Per-window forensic summaries

`GET /api/forensics/{id}/segment-signal` returns, for every stored segment (or the default
plan when none are stored): `rms_dbfs`, `peak_dbfs`, `silence_ratio`, `clipping_ratio`,
`spectral_centroid_hz`, plus the same quality block. It decodes the file **once** and reuses
that waveform for all windows. A silent recording returns `422` with an explicit message
instead of fabricated numbers.

### 4. Error handling

* Corrupt / undecodable container → `422 audio_unreadable`, no stack trace.
* Silent audio → quality report returns `200` with a `silent` warning observation (metadata
  is still useful); segment-signal returns `422` with a specific reason.
* Missing stored media → `410`; other users' records → `404`; anonymous → `401`.
* Empty / non-finite sample arrays are rejected inside the measurement functions.

## Separation from AI prediction

Every response carries `quality.note` and `signal.note`, both stating the measurements
describe the signal and are not evidence of authenticity. The model block is unchanged and
no quality value is fed into the model or used to alter a score. The report PDF (Phase 7)
prints the same caveat.

## Tests

`backend/tests/test_forensics_quality.py` - 12 tests:

* physical sanity of dB measurements, DC/clipping/silence detection, invalid sample rejection;
* API metadata (`bit_depth`, bitrate) and quality block contract;
* silent recording flagged, segment-signal 422 for silence;
* default plan vs stored segments alignment, auth/ownership/410/422 paths;
* corrupt stored file produces a clean 422 without internal details.

Results: see `docs/PHASE_10_REPORT.md` (full suite 137 passed, 1 skipped on SQLite and PostgreSQL).

## Limitations

* Thresholds for the observations are practical heuristics, not calibrated limits.
* `snr_estimate_db` compares speech-percentile level to the quietest frames; it is an
  estimate, labelled as such, not a reference-instrument SNR.
* Measurements cover at most the first 30 s (`FORENSIC_MAX_SECONDS`); the UI states this.
* `GET /api/forensics/{id}` decodes the file twice (signal + quality). This is cheap at
  16 kHz mono but could be merged into one decode later.
* Quality thresholds are not tuned per codec, so heavily compressed MP3s may raise the
  band-limited caution legitimately.
