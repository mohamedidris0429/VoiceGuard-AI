import { useCallback, useEffect, useState } from 'react'
import { BarChart3, Clock, Cpu, RefreshCw, ShieldAlert, ShieldCheck } from 'lucide-react'
import { analyticsApi } from '../services/api'
import {
  ChartCard,
  ConfidenceChart,
  DistributionChart,
  DurationChart,
  TrendChart,
} from '../components/charts'
import { Alert, Button, Card, PageHeader, Skeleton, StatCard } from '../components/ui'
import { formatDuration, formatPercent } from '../utils/format'

const RANGES = [7, 14, 30, 90]

export default function AnalyticsPage() {
  const [range, setRange] = useState(14)
  const [summary, setSummary] = useState(null)
  const [trends, setTrends] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [summaryData, trendsData] = await Promise.all([
        analyticsApi.summary(),
        analyticsApi.trends(range),
      ])
      setSummary(summaryData)
      setTrends(trendsData)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [range])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="animate-fade-in">
      <PageHeader
        eyebrow="Insights"
        title="Audio analytics"
        description="Every number and chart on this page is computed from the analyses stored in your PostgreSQL account."
        actions={
          <>
            <div className="flex items-center gap-1 rounded-xl border border-white/10 bg-white/[0.03] p-1">
              {RANGES.map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setRange(value)}
                  className={`rounded-lg px-2.5 py-1.5 text-[11px] font-semibold transition ${
                    range === value ? 'bg-accent/15 text-accent' : 'text-muted hover:text-ink'
                  }`}
                  aria-pressed={range === value}
                >
                  {value}d
                </button>
              ))}
            </div>
            <Button variant="secondary" size="sm" onClick={load} loading={loading}>
              <RefreshCw size={14} /> Refresh
            </Button>
          </>
        }
      />

      {error ? (
        <Alert
          tone="error"
          className="mb-4"
          title="Could not load analytics"
          action={
            <Button size="sm" variant="secondary" onClick={load}>
              Retry
            </Button>
          }
        >
          {error}
        </Alert>
      ) : null}

      {loading && !summary ? (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="h-[118px]" />
            ))}
          </div>
          <Skeleton className="h-80" />
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              label="Analyses"
              value={summary?.total_analyses ?? 0}
              hint={`${summary?.unavailable ?? 0} unavailable · ${summary?.pending ?? 0} pending`}
              icon={BarChart3}
            />
            <StatCard
              label="Genuine / synthetic"
              value={`${summary?.genuine ?? 0} / ${summary?.synthetic ?? 0}`}
              hint={`${formatPercent(
                summary?.total_analyses ? (summary.genuine / summary.total_analyses) * 100 / 100 : 0,
                0,
              )} classified genuine`}
              icon={ShieldCheck}
            />
            <StatCard
              label="Average duration"
              value={summary?.average_duration != null ? formatDuration(summary.average_duration) : '—'}
              hint={
                summary?.total_audio_seconds != null
                  ? `${formatDuration(summary.total_audio_seconds)} of audio analysed`
                  : 'No audio processed yet'
              }
              icon={Clock}
              tone="teal"
            />
            <StatCard
              label="Average model score"
              value={
                summary?.average_confidence != null ? formatPercent(summary.average_confidence) : '—'
              }
              hint="Mean probability of synthetic speech"
              icon={Cpu}
              tone="warn"
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <ChartCard
              className="lg:col-span-2"
              title="Analysis activity"
              description={`Daily classifications over the last ${range} days`}
            >
              <TrendChart data={trends?.daily || []} />
            </ChartCard>
            <ChartCard title="Classification distribution" description="Completed results by verdict">
              <DistributionChart
                genuine={summary?.genuine || 0}
                synthetic={summary?.synthetic || 0}
                unavailable={summary?.unavailable || 0}
              />
            </ChartCard>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <ChartCard
              title="Confidence distribution"
              description="How synthetic-speech probabilities are spread"
            >
              <ConfidenceChart buckets={trends?.confidence_buckets || []} />
            </ChartCard>
            <ChartCard title="Audio duration statistics" description="Recording lengths by bucket">
              <DurationChart buckets={trends?.duration_buckets || []} />
            </ChartCard>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <h2 className="text-sm font-semibold text-ink">Analysis history summary</h2>
              <p className="mt-0.5 text-xs text-muted">Totals from the first to the latest analysis</p>
              <dl className="mt-4 grid gap-3 sm:grid-cols-3">
                {[
                  ['First analysis', summary?.first_analysis_at ? new Date(summary.first_analysis_at).toLocaleDateString() : '—'],
                  ['Latest analysis', summary?.last_analysis_at ? new Date(summary.last_analysis_at).toLocaleDateString() : '—'],
                  ['Total audio', summary?.total_audio_seconds != null ? formatDuration(summary.total_audio_seconds) : '—'],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
                    <dt className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">
                      {label}
                    </dt>
                    <dd className="mt-1 text-sm font-medium text-ink">{value}</dd>
                  </div>
                ))}
              </dl>
            </Card>

            <Card>
              <h2 className="text-sm font-semibold text-ink">Status breakdown</h2>
              <p className="mt-0.5 text-xs text-muted">Analysis pipeline outcomes</p>
              <ul className="mt-4 space-y-2.5">
                {(trends?.status_breakdown || []).length === 0 ? (
                  <li className="text-[12px] text-muted">No analyses recorded.</li>
                ) : (
                  trends.status_breakdown.map((entry) => (
                    <li key={entry.label} className="flex items-center justify-between gap-3 text-[12px]">
                      <span className="capitalize text-muted">{entry.label}</span>
                      <span className="mono font-semibold text-ink">{entry.count}</span>
                    </li>
                  ))
                )}
              </ul>
              {(summary?.synthetic ?? 0) > 0 ? (
                <p className="mt-4 flex items-start gap-2 rounded-lg border border-danger/20 bg-danger/[0.05] p-2.5 text-[11px] leading-relaxed text-muted">
                  <ShieldAlert size={14} className="mt-0.5 shrink-0 text-danger" />
                  {summary.synthetic} recording(s) scored above the decision threshold. Review them
                  individually — a score is an indicator, not proof.
                </p>
              ) : null}
            </Card>
          </div>
        </div>
      )}
    </div>
  )
}
