import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, BarChart3, CheckCircle2, Layers, RefreshCw } from 'lucide-react'
import { segmentsApi } from '../services/api'
import { Alert, Badge, Button, Card, EmptyState, Skeleton } from './ui'
import { formatPercent } from '../utils/format'

function scoreColour(segment) {
  if (segment.state === 'unsupported') return 'bg-white/15'
  if (segment.state === 'error') return 'bg-danger/70'
  if (segment.score == null) return 'bg-white/15'
  if (segment.score >= 0.5) return 'bg-danger'
  if (segment.score >= 0.3) return 'bg-warn'
  return 'bg-accent'
}

/**
 * Phase 2/6 - segment timeline with explicit coverage and reliability warnings.
 * A partial aggregate never renders as a whole-file verdict: the aggregate label
 * is only shown when `whole_file_reliable` is true.
 */
export function SegmentsPanel({ analysisId, duration }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [computing, setComputing] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await segmentsApi.get(analysisId))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [analysisId])

  useEffect(() => {
    load()
  }, [load])

  const compute = async (force = false) => {
    setComputing(true)
    setError(null)
    try {
      setData(await segmentsApi.compute(analysisId, force ? { force: true } : {}))
    } catch (err) {
      setError(err.message)
    } finally {
      setComputing(false)
    }
  }

  if (loading) {
    return <Skeleton className="h-56" />
  }

  const aggregate = data?.aggregate
  const segments = data?.segments || []
  const total = data?.total_duration || duration || 0
  const reliable = Boolean(aggregate?.whole_file_reliable)

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
            <Layers size={15} className="text-teal" /> Window-by-window analysis
          </h2>
          <p className="mt-1 max-w-2xl text-[12px] leading-relaxed text-muted">
            Each window is scored independently by the same detector. Coverage and reliability are
            reported alongside the scores, and a partial result is never labelled as a whole-file
            verdict.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {aggregate ? (
            <Badge tone={reliable ? 'success' : 'warn'}>
              {reliable ? 'Whole-file coverage' : 'Partial result'}
            </Badge>
          ) : null}
          <Button
            size="sm"
            variant="secondary"
            onClick={() => compute(Boolean(aggregate))}
            loading={computing}
          >
            <RefreshCw size={13} /> {aggregate ? 'Recompute' : 'Score windows'}
          </Button>
        </div>
      </div>

      {error ? (
        <Alert tone="error" className="mt-4" title="Segment analysis failed">
          {error}
        </Alert>
      ) : null}

      {!aggregate ? (
        <EmptyState
          className="py-8"
          icon={BarChart3}
          title="Windows have not been scored yet"
          description="Run the segment analysis to score 4-second windows and measure how much of the recording they cover."
          action={
            <Button size="sm" onClick={() => compute(false)} loading={computing}>
              <CheckCircle2 size={14} /> Score windows
            </Button>
          }
        />
      ) : (
        <>
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
              <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">
                {reliable ? 'Aggregate score' : 'Scored-segment score'}
              </p>
              <p className="mono mt-1 text-lg font-semibold text-ink">
                {aggregate.score != null ? formatPercent(aggregate.score) : '—'}
              </p>
              <p className="mt-0.5 text-[11px] text-muted">
                {reliable
                  ? `Whole-file: ${aggregate.label}`
                  : `Segments only: ${aggregate.scored_label || 'n/a'}`}
              </p>
            </div>
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
              <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">
                Coverage
              </p>
              <p className="mono mt-1 text-lg font-semibold text-ink">
                {formatPercent(aggregate.coverage_ratio, 1)}
              </p>
              <p className="mt-0.5 text-[11px] text-muted">
                {aggregate.coverage_seconds?.toFixed?.(2) ?? aggregate.coverage_seconds}s of{' '}
                {Number(total).toFixed(1)}s
              </p>
            </div>
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
              <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">
                Scored windows
              </p>
              <p className="mono mt-1 text-lg font-semibold text-ink">
                {aggregate.completed_segments}/{segments.length}
              </p>
              <p className="mt-0.5 text-[11px] text-muted">Completed</p>
            </div>
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
              <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">
                Excluded
              </p>
              <p className="mono mt-1 text-lg font-semibold text-ink">
                {aggregate.excluded_segments}
              </p>
              <p className="mt-0.5 text-[11px] text-muted">
                {aggregate.unsupported_segments} short/silent · {aggregate.error_segments} error
              </p>
            </div>
          </div>

          {!reliable ? (
            <Alert tone="warn" className="mt-4" title="Partial coverage — not a whole-file verdict">
              {aggregate.reliability_note ||
                'Coverage is below the 95% threshold or some windows were excluded, so no whole-file label is produced.'}
            </Alert>
          ) : null}

          <div className="mt-5">
            <div className="mb-2 flex items-center justify-between text-[11px] text-muted">
              <span>Timeline</span>
              <span>
                {data.window_seconds}s window · {data.hop_seconds}s hop
              </span>
            </div>
            <div className="relative h-11 w-full overflow-hidden rounded-lg border border-white/[0.06] bg-[#0B1524]">
              {segments.map((segment) => {
                const width = total > 0 ? ((segment.end_seconds - segment.start_seconds) / total) * 100 : 0
                const left = total > 0 ? (segment.start_seconds / total) * 100 : 0
                return (
                  <div
                    key={segment.index}
                    className={`absolute top-0 h-full border-r border-[#0B1524] ${scoreColour(segment)}`}
                    style={{ left: `${left}%`, width: `${Math.max(width, 0.6)}%` }}
                    title={`${segment.start_seconds.toFixed(2)}–${segment.end_seconds.toFixed(2)}s · ${
                      segment.score != null ? formatPercent(segment.score) : segment.state
                    }`}
                  />
                )
              })}
            </div>
            <div className="mt-2 flex flex-wrap gap-3 text-[10px] text-muted">
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-accent" /> Low score
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-warn" /> 30–50%
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-danger" /> ≥50%
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-white/20" /> Not scored
              </span>
            </div>
          </div>

          <details className="mt-4">
            <summary className="cursor-pointer text-[12px] font-semibold text-muted hover:text-ink">
              Per-window detail
            </summary>
            <div className="mt-2 overflow-x-auto">
              <table className="w-full min-w-[520px] text-[12px]">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-[0.08em] text-muted">
                    <th className="px-2 py-1.5">#</th>
                    <th className="px-2 py-1.5">Window</th>
                    <th className="px-2 py-1.5">State</th>
                    <th className="px-2 py-1.5">Score</th>
                    <th className="px-2 py-1.5">Reason</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {segments.map((segment) => (
                    <tr key={segment.index}>
                      <td className="mono px-2 py-1.5 text-muted">{segment.index + 1}</td>
                      <td className="mono px-2 py-1.5 text-muted">
                        {segment.start_seconds.toFixed(2)}–{segment.end_seconds.toFixed(2)}s
                      </td>
                      <td className="px-2 py-1.5">
                        <Badge
                          tone={
                            segment.state === 'done'
                              ? 'neutral'
                              : segment.state === 'error'
                                ? 'danger'
                                : 'warn'
                          }
                        >
                          {segment.state}
                        </Badge>
                      </td>
                      <td className="mono px-2 py-1.5 text-ink">
                        {segment.score != null ? formatPercent(segment.score) : '—'}
                      </td>
                      <td className="px-2 py-1.5 text-muted">{segment.reason || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>

          <p className="mt-3 flex items-start gap-2 text-[11px] leading-relaxed text-muted">
            <AlertTriangle size={13} className="mt-0.5 shrink-0 text-warn" /> {data.caveat}
          </p>
        </>
      )}
    </Card>
  )
}
