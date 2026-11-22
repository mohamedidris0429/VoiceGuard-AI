# Phase 1 — Audio Forensics Workspace

Status: **implemented and tested**. This document records what Phase 1 added on top of the
existing VoiceGuard AI application. No existing module was replaced and no prediction is mocked.

## 1. What was added

| Area | Change |
| --- | --- |
| Backend API | `GET /api/forensics/{analysis_id}` and `GET /api/forensics/{analysis_id}/media` |
| Backend service | `audio_service.forensic_signal()` and `audio_service._band_energy_shares()` |
| Backend schema | `app/schemas/forensics.py` |
| Frontend API | `forensicsApi` in `src/services/api.js` |
| Frontend page | `src/pages/ForensicsPage.jsx` at `/forensics/:analysisId` |
| Frontend components | `src/components/forensics.jsx` (interactive waveform, RMS timeline, band energy bars) |
| Navigation | "Forensics workspace" button on the analysis record; layout title for the route |
| Tests | `backend/tests/test_forensics.py`, `frontend/src/tests/forensics-visual.test.jsx` |

## 2. Workspace capabilities

- **Playback** of the stored recording (authenticated media endpoint, `inline` disposition).
- **Timeline navigation**: native controls, a range slider, ±5 s buttons, and click/arrow-key
  seeking directly on the waveform.
- **Interactive waveform**: 600-bucket peak envelope rendered on a canvas, with a playhead.
- **Spectrogram**: the existing mel-spectrogram PNG endpoint is reused.
- **Loudness over time**: frame RMS envelope (≤160 points) drawn as a lightweight inline SVG.
- **Frequency energy**: relative power share of six fixed bands (0–250 Hz … 4–8 kHz).
- **Audio metadata**: duration, sample rate, Nyquist, channels/layout, container, encoding
  subtype, frame count, file size, analysed window.
- **Model analysis information**: status, prediction, score, threshold, windows, aggregation,
  inference time, parameter count, device and stored failure reason.
- **Explicit framing**: a warning banner plus per-section notes state that these charts are
  measurements of the uploaded file and are **not verified forensic evidence**.

## 3. Honesty and limits

- Charts are computed with librosa from the actual uploaded file; nothing is synthesised.
- No new inference runs in this workspace. The model panel shows the output already stored for
  the analysis (`model_details`), so a pending/unavailable analysis stays pending/unavailable.
- Signal analysis is capped at 30 s (`FORENSIC_MAX_SECONDS`); longer recordings report
  `truncated_for_analysis: true` and the UI explains the bounded window.
- Band energy is a **relative** share of the analysed power spectrum, not an absolute SPL value.
- Hash-based integrity, segments and report verification belong to later phases and are not
  claimed here.

## 4. Memory and CPU behaviour (4 GB target)

- Audio is decoded mono at 16 kHz for at most 30 s (~1.9 MB float32).
- Band power is accumulated in 128-frame blocks; no full-file spectrogram is held in RAM.
- The waveform endpoint decodes at 4 kHz and caps at 600 buckets.
- Spectrograms are rendered server-side and returned as PNG; the browser holds one image.
- The page reuses existing components and adds no chart library.

## 5. Endpoint reference

`GET /api/forensics/{analysis_id}` → `ForensicsOut`

```json
{
  "analysis_id": 12,
  "filename": "sample.wav",
  "source": "upload",
  "file_format": "wav",
  "created_at": "2026-11-19T10:00:00Z",
  "audio": {
    "duration_seconds": 3.0,
    "analysed_seconds": 3.0,
    "sample_rate_hz": 16000,
    "channels": 1,
    "frames": 48000,
    "container": "wav",
    "subtype": "PCM_16",
    "file_size_bytes": 96044,
    "nyquist_hz": 8000.0,
    "channel_layout": "mono",
    "truncated_for_analysis": false
  },
  "waveform": { "peaks": [0.1, 0.4], "buckets": 600, "duration": 3.0 },
  "signal": {
    "rms_timeline": { "times": [0.0, 0.03], "rms": [0.2, 0.6] },
    "band_energy": [{ "label": "0–250 Hz", "low_hz": 0.0, "high_hz": 250.0, "share": 0.41 }],
    "spectral_centroid_hz": 1200.4,
    "spectral_rolloff_hz": 2400.0,
    "zero_crossing_rate": 0.0512,
    "peak_amplitude": 0.9,
    "silence_ratio": 0.02,
    "note": "These charts are measurements of the uploaded signal…"
  },
  "model": {
    "status": "completed",
    "predicted_class": "genuine",
    "model_score": 0.18,
    "model_version": "Vansh180/deepfake-audio-wav2vec2@abc123",
    "threshold": 0.5,
    "windows_analyzed": 1,
    "window_seconds": 4.0,
    "window_scores": [0.18],
    "aggregation": "mean of per-window softmax scores",
    "inference_ms": 900,
    "parameters": 94600000,
    "device": "cpu",
    "failure_reason": null
  },
  "evidence_note": "Waveform, spectrogram and frequency charts are computed from the uploaded file…",
  "disclaimer": "Audio forensics here shows measured signal characteristics only…"
}
```

`GET /api/forensics/{analysis_id}/media` streams the stored file (`audio/wav`, `audio/mpeg`) with
`Cache-Control: private, no-store`. Both endpoints require a bearer token and only serve records
owned by the caller (another user's id returns 404).

## 6. Tests executed (recorded results)

```powershell
cd backend
.venv\Scripts\python.exe -m pytest tests/test_forensics.py
.venv\Scripts\python.exe -m pytest
$env:VOICEGUARD_RUN_MODEL_TESTS = "1"
.venv\Scripts\python.exe -m pytest tests/test_ai.py -m slow

cd ..rontend
npx vitest run
npm run build
```

| Run | Result |
| --- | --- |
| `pytest tests/test_forensics.py` | 8 passed |
| `pytest` (whole suite, SQLite) | 66 collected — 65 passed, 0 failed, 1 skipped (opt-in real-model) |
| `pytest tests/test_ai.py -m slow` | 1 passed (real checkpoint, CPU inference) |
| `npx vitest run` | 13 passed (3 files) |
| `npm run build` | Success |

Live API verification against PostgreSQL 18 on `127.0.0.1:5433` and uvicorn on `127.0.0.1:8000`:
health 200 (`database=connected`), register 201, upload 201 (`pending`, 4.0 s WAV), forensics 200
(16 kHz mono, 64,000 frames, 600 peaks, 126 RMS points, 6 bands summing to 1.000, centroid 616.8 Hz),
media 200 `audio/wav` (RIFF), anonymous 401, cross-user 404, spectrogram 200 PNG (18,874 bytes),
history/analytics/model-status 200, delete 200.

## 7. Windows CMD quick start

```bat
cd F:\sih\backend
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000

:: second terminal
cd F:\sih\frontend
npm run dev
```

Open http://127.0.0.1:5173, sign in, open any analysis, then **Forensics workspace**.

## 8. Known limitations

- No segment-level detection yet (Phase 2); the model panel reflects whole-recording output only.
- Band energy is descriptive, not calibrated; it must never be read as evidence.
- Playback loads the whole file as a blob in the browser (≤20 MB by configuration).
- The workspace trusts the stored container metadata for sample rate/channels while re-probing
  frames/encoding; a replaced file on disk would be detected only by Phase 5 integrity hashing.
