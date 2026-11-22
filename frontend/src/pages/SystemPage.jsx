import { useCallback, useEffect, useState } from 'react'
import {
  Activity,
  Cpu,
  Database,
  ExternalLink,
  RefreshCw,
  Server,
  ShieldCheck,
  Zap,
} from 'lucide-react'
import { API_BASE, systemApi } from '../services/api'
import { useToast } from '../context/ToastContext'
import { Alert, Badge, Button, Card, PageHeader, Skeleton } from '../components/ui'
import { formatDateTime, formatMs } from '../utils/format'

const SECURITY_CONTROLS = [
  ['Password storage', 'bcrypt hashes with per-password salts; plain text is never stored'],
  ['Session security', 'JWT access tokens signed with a server-side key and expiry'],
  ['Ownership checks', 'Every record query is scoped to the authenticated user'],
  ['Upload validation', 'Container headers, extension, size, duration and sample rate are verified'],
  ['Rate limiting', 'Sliding window limits on authentication and analysis endpoints'],
  ['Path safety', 'Stored files use opaque UUID names; paths are never returned to clients'],
  ['CORS', 'Restricted to configured frontend origins'],
  ['Error handling', 'Centralised handlers return safe messages without stack traces'],
]

function StatusRow({ icon: Icon, label, value, tone, detail }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-white/[0.05] py-3 last:border-0">
      <div className="flex items-start gap-2.5">
        <span className="mt-0.5 rounded-lg border border-white/10 bg-white/[0.03] p-1.5 text-muted">
          <Icon size={14} aria-hidden />
        </span>
        <div>
          <p className="text-[13px] font-medium text-ink">{label}</p>
          {detail ? <p className="mt-0.5 text-[11px] leading-relaxed text-muted">{detail}</p> : null}
        </div>
      </div>
      <Badge tone={tone}>{value}</Badge>
    </div>
  )
}

export default function SystemPage() {
  const toast = useToast()
  const [health, setHealth] = useState(null)
  const [model, setModel] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [loadingModel, setLoadingModel] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [healthData, modelData] = await Promise.all([systemApi.health(), systemApi.modelStatus()])
      setHealth(healthData)
      setModel(modelData)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const preloadModel = async () => {
    setLoadingModel(true)
    try {
      const data = await systemApi.modelStatus(true)
      setModel(data)
      if (data.available) toast.success('Model loaded and ready for inference.')
      else toast.error(data.detail || 'The model could not be loaded.')
    } catch (err) {
      toast.error(err.message)
    } finally {
      setLoadingModel(false)
    }
  }

  return (
    <div className="animate-fade-in">
      <PageHeader
        eyebrow="Diagnostics"
        title="System status"
        description="Health of the API, database connection and the pretrained detection model, plus the controls protecting your data."
        actions={
          <Button variant="secondary" onClick={load} loading={loading}>
            <RefreshCw size={14} /> Refresh
          </Button>
        }
      />

      {error ? (
        <Alert tone="error" className="mb-4" title="Could not read system status">
          {error}
        </Alert>
      ) : null}

      {loading && !health ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <div className="mb-2 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
                <Server size={15} className="text-accent" /> API & database
              </h2>
              <Badge tone={health?.status === 'operational' ? 'success' : 'warn'}>
                {health?.status || 'unknown'}
              </Badge>
            </div>

            <StatusRow
              icon={Activity}
              label="API service"
              value={health ? 'Online' : 'Unknown'}
              tone={health ? 'success' : 'warn'}
              detail={`${health?.app || 'VoiceGuard AI'} v${health?.version || '—'} · ${health?.environment || '—'} environment`}
            />
            <StatusRow
              icon={Database}
              label="PostgreSQL connection"
              value={health?.database === 'connected' ? 'Connected' : 'Unavailable'}
              tone={health?.database === 'connected' ? 'success' : 'danger'}
              detail="Health check executes SELECT 1 on the configured database."
            />
            <StatusRow
              icon={Activity}
              label="Uptime"
              value={health ? `${Math.floor((health.uptime_seconds || 0) / 60)} min` : '—'}
              tone="neutral"
              detail={`Last checked ${formatDateTime(health?.timestamp)}`}
            />
            <StatusRow
              icon={ShieldCheck}
              label="Last successful analysis"
              value={health?.last_successful_analysis_at ? 'Recorded' : 'None'}
              tone={health?.last_successful_analysis_at ? 'success' : 'neutral'}
              detail={
                health?.last_successful_analysis_at
                  ? formatDateTime(health.last_successful_analysis_at)
                  : 'Run an analysis to populate this value.'
              }
            />

            <div className="mt-4 flex flex-wrap gap-2">
              <a
                href={`${API_BASE.replace(/\/api$/, '')}/api/docs`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-[12px] font-semibold text-ink transition hover:border-accent/30"
              >
                Swagger API docs <ExternalLink size={12} />
              </a>
              <span className="mono inline-flex items-center rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-[11px] text-muted">
                {API_BASE}
              </span>
            </div>
          </Card>

          <Card>
            <div className="mb-2 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
                <Cpu size={15} className="text-teal" /> AI model
              </h2>
              <Badge tone={model?.available ? 'success' : model?.loaded ? 'danger' : 'warn'}>
                {model?.available ? 'Available' : model?.loaded ? 'Unavailable' : 'Not loaded'}
              </Badge>
            </div>

            <dl className="space-y-2.5 text-[12px]">
              {[
                ['Model', model?.model_id || '—'],
                ['Version / revision', model?.model_version || '—'],
                ['Device', `${model?.device || 'cpu'} (CPU inference)`],
                ['Parameters', model?.parameters ? `${(model.parameters / 1_000_000).toFixed(1)} M` : '—'],
                ['Sample rate', `${model?.sample_rate || 16000} Hz mono`],
                ['Window', `${model?.window_seconds ?? 4}s × up to ${model?.max_windows ?? 3} windows`],
                ['Decision threshold', model?.threshold ?? 0.5],
                ['Load time', formatMs(model?.load_ms)],
              ].map(([label, value]) => (
                <div key={label} className="flex items-start justify-between gap-3">
                  <dt className="text-muted">{label}</dt>
                  <dd className="max-w-[62%] break-words text-right font-medium text-ink">{value}</dd>
                </div>
              ))}
            </dl>

            {model && Object.keys(model.labels || {}).length > 0 ? (
              <p className="mono mt-3 rounded-lg border border-white/[0.06] bg-[#0B1524] p-2.5 text-[11px] text-muted">
                labels: {JSON.stringify(model.labels)}
              </p>
            ) : null}

            {!model?.available ? (
              <Alert tone="warn" className="mt-3">
                {model?.detail ||
                  'The model loads on the first analysis. Preload it now to verify that the weights are available.'}
              </Alert>
            ) : null}

            <Button className="mt-3 w-full" variant="secondary" onClick={preloadModel} loading={loadingModel}>
              <Zap size={14} /> Load model now
            </Button>
          </Card>
        </div>
      )}

      <Card className="mt-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
          <ShieldCheck size={15} className="text-accent" /> Security controls
        </h2>
        <div className="mt-3 grid gap-2.5 sm:grid-cols-2">
          {SECURITY_CONTROLS.map(([label, detail]) => (
            <div key={label} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
              <p className="text-[12px] font-semibold text-ink">{label}</p>
              <p className="mt-0.5 text-[11px] leading-relaxed text-muted">{detail}</p>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}
