# Phase 9 - Frontend / backend integration audit

Status: **audited; integration gaps fixed; production build passes.** Browser click-through
was not performed in this environment (see limitations).

## Screen-by-screen audit

| screen | backend | state |
| --- | --- | --- |
| Login / Register | `POST /auth/login`, `/auth/register`, session restored via `/auth/me` | wired |
| Dashboard | `/analytics/summary`, `/analytics/trends`, `/history?page_size=5`, `/model/status`, `/health` | wired, real numbers |
| Analyse audio (upload) | `/audio/limits/info`, `/audio/upload`, `/audio/analyze`, `/audio/{id}` | wired with progress + retry |
| Record | MediaRecorder → in-browser WAV → upload → analyse | wired |
| **Live monitor** (new) | `/stream/sessions*` | wired, labelled near-real-time |
| Analysis detail | `/audio/{id}`, waveform, spectrogram, **segments**, report download, delete, re-run | wired |
| Forensics workspace | `/forensics/{id}`, `/media`, `/spectrogram` | wired |
| History | `/history` search/filter/sort/paginate, delete, report | wired; table class bug fixed |
| Compare | `/audio/compare` | wired, explicit no-speaker-verification warning |
| Analytics | `/analytics/summary`, `/analytics/trends` | wired |
| Profile | `/auth/me` PATCH, `/auth/change-password` | wired |
| System | `/health`, `/model/status?load=true` | wired |

## Fixes made

1. **HistoryPage class bug** - `dateCellClass` evaluated to the literal string `"cellPadding"`,
   so date cells lost their styling; replaced with valid template-string classes and removed
   dead duplicates.
2. **Segment results were unreachable from the UI** - added the segment timeline panel to the
   analysis detail page (Phase 6 component), including compute/recompute actions.
3. **Live monitoring was missing** - added `/live` page, nav entry, route and API client
   covering start, per-chunk scoring, stop, discard, error and permission-denied states.
4. **Report parity** - the PDF now includes the same partial-result warning the UI shows.

## No placeholder functionality left

Grep audit for `TODO`, `FIXME`, `mock`, `placeholder`, `hardcoded` across `backend/app` and
`frontend/src` found no mock data paths. All charts and counters read server values; empty
states appear when the API returns zero rows.

## Verification performed

* `npm run build` (Vite production) - success.
* Backend contracts used by these screens are covered by the test suite (137 passed,
  1 skipped on SQLite and PostgreSQL), including history/analytics/reports/segments/stream.
* Static inspection of every page's API calls against the router definitions.

## Not verified / limitations

* No live browser session or screenshot review was performed, so layout at specific
  viewports, keyboard navigation and microphone permission prompts are **not** confirmed.
* `LivePage` has no automated test; its API contract is tested server-side.
* End-to-end flows (register → upload → report) were not driven through a browser; only the
  underlying endpoints are tested.
* The frontend stores the JWT in `localStorage` (see Phase 8).
