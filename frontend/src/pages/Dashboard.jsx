import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Activity,
  ArrowRight,
  Clock,
  Cpu,
  Database,
  FileAudio,
  Mic,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Upload,
} from 'lucide-react'
import { analyticsApi, historyApi, systemApi } from '../services/api'
import { useAuth } from '../context/AuthContext'
import { ChartCard, DistributionChart, TrendChart } from '../components/charts'
import { Alert, Badge, Button, Card, EmptyState, PageHeader, Skeleton, StatCard } from '../components/ui'
import { VerdictBadge } from '../components/verdict'
import {
  DISCLAIMER,
  formatDateTime,
  formatDuration,
  formatPercent,
} from '../utils/format'

export default function Dashboard() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [summary, setSummary] = useState(null)
  const [trends, setTrends] = useState(null)
  const [recent, setRecent] = useState(null)
  const [model, setModel] = useState(null)
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [summaryData, trendsData, recentData, modelData, healthData] = await Promise.all([
        analyticsApi.summary(),
        analyticsApi.trends(14),
        historyApi.list({ page: 1, page_size: 5 }),
        systemApi.modelStatus(),
        systemApi.health(),
      ])
      setSummary(summaryData)
      setTrends(trendsData)
      setRecent(recentData)
      setModel(modelData)
      setHealth(healthData)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const firstName = (user?.name || '').split(' ')[0] || 'there'
  const isEmpty = summary && summary.total_analyses === 0

  const modelTone = model?.available ? 'success' : model?.loaded ? 'danger' : 'warn'
  const modelLabel = model?.available ? 'Ready' : model?.loaded ? 'Unavailable' : 'Idle · loads on demand'

  return (
    <div className="animate-fade-in">
      <PageHeader
        eyebrow="Overview"
        title={`Welcome back, ${firstName}`}
        description="Live statistics from your voice authenticity analyses, computed directly from the database."
        actions={
          <>
            <Button variant="secondary" onClick={() => navigate('/record')}>
              <Mic size={15} /> Record
            </Button>
            <Button onClick={() => navigate('/upload')}>
              <Upload size={15} /> Analyse audio
            </Button>
          </>
        }
      />

      {error ? (
        <Alert
          tone="error"
          className="mb-5"
          title="Could not load dashboard data"
          action={
            <Button size="sm" variant="secondary" onClick={load}>
              <RefreshCw size={13} /> Try again
            </Button>
          }
        >
          {error}
        </Alert>
      ) : null}

      {loading ? (
        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="h-[118px]" />
            ))}
          </div>
          <div className="grid gap-4 lg:grid-cols-3">
            <Skeleton className="h-72 lg:col-span-2" />
            <Skeleton className="h-72" />
          </div>
        </div>
      ) : (
        <div className="space-y-5">
          {isEmpty ? (
            <Card className="border-accent/20 bg-accent/[0.03] p-6">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-start gap-3">
                  <span className="rounded-xl border border-accent/25 bg-accent/10 p-2.5 text-accent">
                    <FileAudio size={19} aria-hidden />
                  </span>
                  <div>
                    <h2 className="text-sm font-semibold text-ink">Run your first analysis</h2>
                    <p className="mt-1 max-w-xl text-[13px] leading-relaxed text-muted">
                      Upload a WAV or MP3 recording (1–60 seconds) or capture one with your
                      microphone. The pretrained detection model runs on CPU and returns a
                      probabilistic verdict with model version and score.
                    </p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button variant="secondary" size="sm" onClick={() => navigate('/record')}>
                    <Mic size={14} /> Record
                  </Button>
                  <Button size="sm" onClick={() => navigate('/upload')}>
                    <Upload size={14} /> Upload
                  </Button>
                </div>
              </div>
            </Card>
          ) : null}

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              label="Total analyses"
              value={summary?.total_analyses ?? 0}
              hint={summary?.average_duration ? `Avg ${formatDuration(summary.average_duration)} per clip` : 'No completed analyses yet'}
              icon={Activity}
            />
            <StatCard
              label="Likely genuine"
              value={summary?.genuine ?? 0}
              hint={`${formatPercent(
                summary?.total_analyses ? summary.genuine / summary.total_analyses : 0,
                0,
              )} of all analyses`}
              icon={ShieldCheck}
            />
            <StatCard
              label="Potentially synthetic"
              value={summary?.synthetic ?? 0}
              hint={`${formatPercent(
                summary?.total_analyses ? summary.synthetic / summary.total_analyses : 0,
                0,
              )} of all analyses`}
              icon={ShieldAlert}
              tone="danger"
            />
            <StatCard
              label="Avg synthetic probability"
              value={summary?.average_confidence != null ? formatPercent(summary.average_confidence) : '—'}
              hint={
                summary?.unavailable
                  ? `${summary.unavailable} record(s) could not be analysed`
                  : 'Mean model score across completed analyses'
              }
              icon={Cpu}
              tone="teal"
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <ChartCard
              className="lg:col-span-2"
              title="Analysis activity"
              description="Analyses per day over the last 14 days"
              action={
                <Link to="/analytics" className="inline-flex items-center gap-1 text-[12px] font-semibold text-accent hover:text-[#4ade80]">
                  Analytics <ArrowRight size={12} />
                </Link>
              }
            >
              <TrendChart data={trends?.daily || []} />
            </ChartCard>

            <ChartCard title="Classification distribution" description="All analysed recordings">
              <DistributionChart
                genuine={summary?.genuine || 0}
                synthetic={summary?.synthetic || 0}
                unavailable={summary?.unavailable || 0}
              />
            </ChartCard>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-ink">Recent activity</h2>
                  <p className="mt-0.5 text-xs text-muted">Latest five analyses from your account</p>
                </div>
                <Link to="/history" className="text-[12px] font-semibold text-accent hover:text-[#4ade80]">
                  View all
                </Link>
              </div>

              {recent && recent.items.length > 0 ? (
                <ul className="divide-y divide-white/[0.05]">
                  {recent.items.map((item) => (
                    <li key={item.id}>
                      <Link
                        to={`/analysis/${item.id}`}
                        className="flex flex-wrap items-center gap-3 py-3 transition hover:bg-white/[0.02]"
                      >
                        <span className="rounded-lg border border-white/10 bg-white/[0.03] p-2 text-muted">
                          <FileAudio size={15} aria-hidden />
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-[13px] font-medium text-ink">{item.filename}</p>
                          <p className="text-[11px] text-muted">
                            {formatDateTime(item.created_at)} · {formatDuration(item.audio_duration)}
                          </p>
                        </div>
                        <div className="flex items-center gap-3">
                          {item.model_score != null ? (
                            <span className="mono hidden text-[12px] text-muted sm:inline">
                              {formatPercent(item.model_score)}
                            </span>
                          ) : null}
                          <VerdictBadge prediction={item.predicted_class} status={item.analysis_status} />
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState
                  icon={FileAudio}
                  title="No analyses yet"
                  description="Your recordings and their verdicts will appear here."
                  action={
                    <Button size="sm" onClick={() => navigate('/upload')}>
                      <Upload size={14} /> Upload a recording
                    </Button>
                  }
                />
              )}
            </Card>

            <Card>
              <h2 className="text-sm font-semibold text-ink">System status</h2>
              <p className="mt-0.5 text-xs text-muted">Live health of the detection stack</p>

              <dl className="mt-4 space-y-3 text-[13px]">
                <div className="flex items-center justify-between gap-3">
                  <dt className="flex items-center gap-2 text-muted">
                    <Database size={14} /> Database
                  </dt>
                  <dd>
                    <Badge tone={health?.database === 'connected' ? 'success' : 'danger'}>
                      {health?.database === 'connected' ? 'Connected' : 'Unavailable'}
                    </Badge>
                  </dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="flex items-center gap-2 text-muted">
                    <Cpu size={14} /> AI model
                  </dt>
                  <dd>
                    <Badge tone={modelTone}>{modelLabel}</Badge>
                  </dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="flex items-center gap-2 text-muted">
                    <Activity size={14} /> API
                  </dt>
                  <dd>
                    <Badge tone={health?.status === 'operational' ? 'success' : 'warn'}>
                      {health?.status || 'Unknown'}
                    </Badge>
                  </dd>
                </div>
                <div className="flex items-start justify-between gap-3">
                  <dt className="flex items-center gap-2 text-muted">
                    <Clock size={14} /> Last successful analysis
                  </dt>
                  <dd className="text-right text-[12px] text-ink">
                    {summary?.last_successful_at ? formatDateTime(summary.last_successful_at) : 'None yet'}
                  </dd>
                </div>
              </dl>

              <p className="mt-4 rounded-lg border border-white/[0.06] bg-white/[0.02] p-2.5 text-[11px] leading-relaxed text-muted">
                Model: <span className="text-ink">{model?.model_id || 'not reported'}</span>
                <br />
                Device: {model?.device || 'cpu'} · window {model?.window_seconds ?? 4}s
              </p>

              <Button variant="secondary" size="sm" className="mt-4 w-full" onClick={() => navigate('/system')}>
                Open system status <ArrowRight size={13} />
              </Button>
            </Card>
          </div>

          <Alert tone="warn" title="Interpret results carefully">
            {DISCLAIMER} A positive result does not identify a speaker and a negative result does not
            prove authenticity.
          </Alert>
        </div>
      )}
    </div>
  )
}
