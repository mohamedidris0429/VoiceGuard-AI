# Phase 6 - Dashboard and history

Status: **complete and wired to real APIs**.

## What already existed (preserved)

The dashboard, history, analytics, comparison, profile and system pages were already bound to
real endpoints (`/api/analytics/*`, `/api/history`, `/api/audio/*`, `/api/system`). No mock
data or hardcoded statistics were found in those pages.

## Added in this phase

### Segment timeline with coverage warnings

`frontend/src/components/segments.jsx` + `AnalysisDetail` integration:

* fetches `GET /api/forensics/{id}/segments`; shows an explicit empty state and a
  "Score windows" action when nothing is stored yet;
* renders a proportional timeline where each window is coloured by score band, with
  not-scored windows in grey and errored windows in red;
* headline metrics: aggregate score, coverage %, scored/excluded counts;
* when `whole_file_reliable` is false it shows a prominent amber warning with
  `reliability_note` and labels the number "Scored-segment score", never a whole-file verdict;
* collapsible per-window table (window, state, score, reason) and the server `caveat`.

### History table fix

`HistoryPage.jsx` contained a broken class-name expression
(`const dateCellClass = "cellPadding" + ...`, producing a literal `cellPadding` class) and
unused duplicated cell classes. Replaced with template-string classes so date cells and mono
cells receive valid Tailwind classes. No behaviour or layout redesign.

## States and ownership

* Dashboard/history expose loading skeletons, error panels with retry, and filtered-empty vs
  truly-empty states.
* Every list/detail request is scoped by `user_id` server-side; the UI relies on that and
  shows "not found" for foreign ids.
* Pagination is server-driven (`page`, `page_size`), sorting has a stable id tiebreaker.

## Verification

* `npm run build` succeeds (see `docs/PHASE_10_REPORT.md`).
* API behaviour is covered by `backend/tests/test_records.py` (history filters/sorting,
  analytics totals, report endpoints) which passed on SQLite and PostgreSQL.
* The new components were **not** exercised in a live browser here; the visual result was
  verified only by a successful production build.

## Limitations

* No frontend unit test was added for the segment timeline (the existing React tests cover
  formatting and the forensics visual helpers).
* Chart components are inline SVG with no external chart dependency; very large histories are
  paginated before charting, so no unbounded rendering.
