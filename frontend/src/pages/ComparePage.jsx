import { useState } from 'react'
import { GitCompare, Loader2, ShieldAlert, X } from 'lucide-react'
import { audioApi } from '../services/api'
import { useToast } from '../context/ToastContext'
import { DropZone, Spectrogram } from '../components/audio'
import { ScoreBar, VerdictBadge } from '../components/verdict'
import { Alert, Badge, Button, Card, EmptyState, PageHeader, ProgressBar } from '../components/ui'
import { formatDateTime, formatDuration, formatPercent } from '../utils/format'

const MAX_MB = 20

function validate(file) {
  const extension = (file.name.split('.').pop() || '').toLowerCase()
  if (!['wav', 'mp3'].includes(extension)) return 'Only .wav and .mp3 files are supported.'
  if (file.size > MAX_MB * 1024 * 1024) return `File must be smaller than ${MAX_MB} MB.`
  return ''
}

function ComparisonCard({ analysis, label }) {
  const details = analysis.model_details || {}
  return (
    <Card className="space-y-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">{label}</p>
          <h2 className="truncate text-sm font-semibold text-ink" title={analysis.filename}>
            {analysis.filename}
          </h2>
          <p className="text-[11px] text-muted">
            {formatDateTime(analysis.created_at)} · #{analysis.id}
          </p>
        </div>
        <VerdictBadge prediction={analysis.predicted_class} status={analysis.analysis_status} />
      </div>

      {analysis.analysis_status === 'completed' ? (
        <ScoreBar score={analysis.model_score} threshold={details.threshold ?? 0.5} />
      ) : (
        <Alert tone="warn">{analysis.failure_reason || 'No model result is available.'}</Alert>
      )}

      <dl className="grid grid-cols-2 gap-2 text-[12px]">
        {[
          ['Duration', formatDuration(analysis.audio_duration)],
          ['Sample rate', analysis.sample_rate ? `${analysis.sample_rate} Hz` : '—'],
          ['Channels', analysis.channels ?? '—'],
          ['Format', (analysis.file_format || '—').toUpperCase()],
          ['Windows', details.windows_analyzed ?? '—'],
          ['Model', analysis.model_version || '—'],
        ].map(([term, value]) => (
          <div key={term} className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-2.5">
            <dt className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">{term}</dt>
            <dd className="mt-0.5 truncate text-ink" title={String(value)}>
              {value}
            </dd>
          </div>
        ))}
      </dl>

      <Spectrogram analysisId={analysis.id} alt={`Spectrogram for ${analysis.filename}`} />
    </Card>
  )
}

export default function ComparePage() {
  const toast = useToast()
  const [fileA, setFileA] = useState(null)
  const [fileB, setFileB] = useState(null)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState(0)

  const choose = (setter) => (file) => {
    const message = validate(file)
    if (message) {
      setError(message)
      return
    }
    setError('')
    setter(file)
  }

  const submit = async () => {
    if (!fileA || !fileB) return
    setBusy(true)
    setError('')
    setProgress(0)
    try {
      const data = await audioApi.compare(fileA, fileB, setProgress)
      setResult(data)
      toast.success('Both recordings analysed.')
    } catch (err) {
      setError(err.message)
      toast.error(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="animate-fade-in">
      <PageHeader
        eyebrow="Side by side"
        title="Compare two recordings"
        description="Each recording is validated and analysed independently by the same detection pipeline, then presented side by side."
      />

      <Alert tone="warn" className="mb-4" title="No speaker verification is performed">
        These are two independent spoof-detection results. VoiceGuard AI does not implement a
        speaker-verification model, so nothing here implies that the two recordings belong to the
        same person (or to different people).
      </Alert>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="space-y-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">Recording A</p>
          <DropZone file={fileA} onFileSelected={choose(setFileA)} onClear={() => setFileA(null)} disabled={busy} />
        </Card>
        <Card className="space-y-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">Recording B</p>
          <DropZone file={fileB} onFileSelected={choose(setFileB)} onClear={() => setFileB(null)} disabled={busy} />
        </Card>
      </div>

      {error ? (
        <Alert tone="error" className="mt-4" title="Comparison could not run">
          {error}
        </Alert>
      ) : null}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button onClick={submit} disabled={!fileA || !fileB || busy} loading={busy}>
          {busy ? <Loader2 size={15} className="animate-spin" /> : <GitCompare size={15} />}
          {busy ? 'Analysing both recordings…' : 'Compare recordings'}
        </Button>
        <Button
          variant="ghost"
          onClick={() => {
            setFileA(null)
            setFileB(null)
            setResult(null)
            setError('')
          }}
          disabled={busy || (!fileA && !fileB && !result)}
        >
          <X size={14} /> Clear
        </Button>
      </div>

      {busy ? (
        <div className="mt-3 max-w-md space-y-2">
          <p className="text-[12px] text-muted">
            Uploading and scoring both files. Two inference passes run on CPU, so this can take a
            little longer than a single analysis.
          </p>
          <ProgressBar value={progress} showLabel />
        </div>
      ) : null}

      {result ? (
        <div className="mt-6 space-y-4">
          <Card className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <span className="rounded-xl border border-teal/25 bg-teal/10 p-2.5 text-teal">
                <GitCompare size={18} aria-hidden />
              </span>
              <div>
                <h2 className="text-sm font-semibold text-ink">Comparison summary</h2>
                <p className="text-[12px] text-muted">
                  Duration difference{' '}
                  <span className="font-semibold text-ink">
                    {result.duration_delta_seconds != null
                      ? `${result.duration_delta_seconds > 0 ? '+' : ''}${result.duration_delta_seconds.toFixed(2)} s`
                      : '—'}
                  </span>{' '}
                  · Score difference{' '}
                  <span className="font-semibold text-ink">
                    {result.score_delta != null
                      ? `${result.score_delta > 0 ? '+' : ''}${formatPercent(result.score_delta)}`
                      : '—'}
                  </span>
                </p>
              </div>
            </div>
            <div className="flex gap-2">
              <Badge tone="success">A: {formatPercent(result.left.model_score ?? 0)}</Badge>
              <Badge tone="danger">B: {formatPercent(result.right.model_score ?? 0)}</Badge>
            </div>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <ComparisonCard analysis={result.left} label="Recording A" />
            <ComparisonCard analysis={result.right} label="Recording B" />
          </div>

          <Alert tone="warn">{result.disclaimer}</Alert>
        </div>
      ) : (
        <Card className="mt-6">
          <EmptyState
            icon={ShieldAlert}
            title="No comparison yet"
            description="Select two recordings and run the comparison to see each verdict, score, metadata and spectrogram."
          />
        </Card>
      )}
    </div>
  )
}
