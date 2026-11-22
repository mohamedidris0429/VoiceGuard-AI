import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  Activity,
  ArrowLeft,
  Cpu,
  Download,
  FileAudio,
  FileText,
  Loader2,
  Play,
  RefreshCw,
  Trash2,
} from 'lucide-react'
import { audioApi, reportsApi } from '../services/api'
import { useToast } from '../context/ToastContext'
import { Spectrogram, Waveform } from '../components/audio'
import { SegmentsPanel } from '../components/segments'
import { ScoreBar, VerdictPanel } from '../components/verdict'
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  Modal,
  PageHeader,
  Skeleton,
} from '../components/ui'
import {
  formatBytes,
  formatDateTime,
  formatDuration,
  formatMs,
  formatPercent,
  statusLabel,
  statusTone,
} from '../utils/format'

function MetaGrid({ items }) {
  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      {items.map((item) => (
        <div key={item.label} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
          <dt className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">
            {item.label}
          </dt>
          <dd className="mt-1 truncate text-[13px] font-medium text-ink" title={String(item.value)}>
            {item.value}
          </dd>
        </div>
      ))}
    </dl>
  )
}

export default function AnalysisDetail() {
  const { analysisId } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const [analysis, setAnalysis] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [downloading, setDownloading] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [running, setRunning] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await audioApi.get(analysisId)
      setAnalysis(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [analysisId])

  useEffect(() => {
    load()
  }, [load])

  const runAnalysis = async () => {
    setRunning(true)
    try {
      const updated = await audioApi.analyze(analysisId)
      setAnalysis(updated)
      if (updated.analysis_status === 'completed') toast.success('Analysis completed.')
      else toast.error(updated.failure_reason || 'The model could not analyse this recording.')
    } catch (err) {
      toast.error(err.message)
    } finally {
      setRunning(false)
    }
  }

  const downloadReport = async () => {
    setDownloading(true)
    try {
      const { blob, filename } = await reportsApi.download(analysisId)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = filename
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      setTimeout(() => URL.revokeObjectURL(url), 4000)
      toast.success('PDF report downloaded.')
    } catch (err) {
      toast.error(err.message)
    } finally {
      setDownloading(false)
    }
  }

  const deleteAnalysis = async () => {
    setDeleting(true)
    try {
      await audioApi.remove(analysisId)
      toast.success('Analysis deleted.')
      navigate('/history', { replace: true })
    } catch (err) {
      toast.error(err.message)
      setDeleting(false)
      setConfirmOpen(false)
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-40" />
        <div className="grid gap-4 lg:grid-cols-3">
          <Skeleton className="h-72 lg:col-span-2" />
          <Skeleton className="h-72" />
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-4">
        <Link to="/history" className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-muted hover:text-ink">
          <ArrowLeft size={14} /> Back to history
        </Link>
        <Alert
          tone="error"
          title="This analysis could not be loaded"
          action={
            <Button size="sm" variant="secondary" onClick={load}>
              <RefreshCw size={13} /> Retry
            </Button>
          }
        >
          {error}
        </Alert>
      </div>
    )
  }

  if (!analysis) {
    return (
      <EmptyState
        icon={FileAudio}
        title="Analysis not found"
        description="It may have been deleted, or it belongs to another account."
        action={<Button onClick={() => navigate('/history')}>Open history</Button>}
      />
    )
  }

  const details = analysis.model_details || {}
  const features = analysis.audio_features || {}
  const completed = analysis.analysis_status === 'completed'

  return (
    <div className="animate-fade-in space-y-5">
      <Link to="/history" className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-muted hover:text-ink">
        <ArrowLeft size={14} /> Back to history
      </Link>

      <PageHeader
        eyebrow={`Analysis #${analysis.id}`}
        title={analysis.filename}
        description={`Analysed ${formatDateTime(analysis.created_at)} · ${formatDuration(analysis.audio_duration)} · ${
          analysis.source === 'recording' ? 'microphone recording' : analysis.source === 'comparison' ? 'comparison clip' : 'file upload'
        }`}
        actions={
          <>
            <Button variant="secondary" onClick={() => navigate(`/forensics/${analysis.id}`)}>
              <Activity size={15} /> Forensics workspace
            </Button>
            {completed ? (
              <Button onClick={downloadReport} loading={downloading}>
                {downloading ? <Loader2 size={15} className="animate-spin" /> : <Download size={15} />}
                PDF report
              </Button>
            ) : null}
            <Button variant="danger" onClick={() => setConfirmOpen(true)}>
              <Trash2 size={15} /> Delete
            </Button>
          </>
        }
      />

      <VerdictPanel analysis={analysis} />

      {analysis.analysis_status === 'pending' ? (
        <Card className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-ink">This recording has not been analysed yet</p>
            <p className="text-[12px] text-muted">Run the detection model now to produce a verdict.</p>
          </div>
          <Button onClick={runAnalysis} loading={running}>
            <Play size={15} /> Run analysis
          </Button>
        </Card>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <h2 className="mb-3 text-sm font-semibold text-ink">Waveform</h2>
          <Waveform analysisId={analysis.id} />
          <h2 className="mb-3 mt-5 text-sm font-semibold text-ink">Spectrogram</h2>
          <Spectrogram analysisId={analysis.id} />
        </Card>

        <div className="space-y-4">
          <Card>
            <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
              <FileAudio size={15} className="text-teal" /> Recording
            </h2>
            <MetaGrid
              items={[
                { label: 'Format', value: (analysis.file_format || '—').toUpperCase() },
                { label: 'Duration', value: formatDuration(analysis.audio_duration) },
                { label: 'Sample rate', value: analysis.sample_rate ? `${analysis.sample_rate} Hz` : '—' },
                { label: 'Channels', value: analysis.channels ?? '—' },
                { label: 'File size', value: formatBytes(analysis.file_size_bytes) },
                { label: 'Status', value: statusLabel(analysis.analysis_status) },
              ]}
            />
          </Card>

          <Card>
            <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
              <Cpu size={15} className="text-accent" /> Model
            </h2>
            {completed ? (
              <div className="space-y-3">
                <ScoreBar score={analysis.model_score} threshold={details.threshold ?? 0.5} />
                <dl className="space-y-2 text-[12px]">
                  {[
                    ['Model version', analysis.model_version || '—'],
                    ['Windows analysed', details.windows_analyzed ?? '—'],
                    ['Window length', `${details.window_seconds ?? 4}s`],
                    ['Threshold', formatPercent(details.threshold ?? 0.5, 0)],
                    ['Processing time', formatMs(analysis.analysis_duration_ms)],
                  ].map(([term, value]) => (
                    <div key={term} className="flex items-start justify-between gap-3">
                      <dt className="text-muted">{term}</dt>
                      <dd className="max-w-[60%] break-words text-right font-medium text-ink">{value}</dd>
                    </div>
                  ))}
                </dl>
                {Array.isArray(details.window_scores) && details.window_scores.length > 0 ? (
                  <div className="rounded-lg border border-white/[0.06] bg-[#0B1524] p-2.5">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">
                      Per-window synthetic scores
                    </p>
                    <p className="mono mt-1 text-[12px] text-ink">
                      {details.window_scores.map((score) => Number(score).toFixed(3)).join(' · ')}
                    </p>
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="space-y-2 text-[12px] text-muted">
                <Badge tone={statusTone(analysis.analysis_status)}>
                  {statusLabel(analysis.analysis_status)}
                </Badge>
                <p className="leading-relaxed">
                  {analysis.failure_reason ||
                    'No model output is stored for this record. Run the analysis again when the model is available.'}
                </p>
              </div>
            )}
          </Card>
        </div>
      </div>

      <SegmentsPanel analysisId={analysis.id} duration={analysis.audio_duration} />

      {analysis.audio_features ? (
        <Card>
          <h2 className="mb-1 text-sm font-semibold text-ink">Descriptive signal features</h2>
          <p className="mb-3 text-[12px] leading-relaxed text-muted">
            These measurements describe the audio. The classifier does not use them to reach its
            verdict, and they must not be read as evidence on their own.
          </p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ['Spectral centroid', `${features.spectral_centroid_hz ?? '—'} Hz`],
              ['Spectral roll-off', `${features.spectral_rolloff_hz ?? '—'} Hz`],
              ['Spectral bandwidth', `${features.spectral_bandwidth_hz ?? '—'} Hz`],
              ['Zero-crossing rate', features.zero_crossing_rate ?? '—'],
              ['RMS energy', features.rms_energy ?? '—'],
              ['Peak amplitude', features.peak_amplitude ?? '—'],
              ['Silence ratio', formatPercent(features.silence_ratio ?? 0, 1)],
              ['Analysed audio', formatDuration(features.analysed_seconds)],
            ].map(([label, value]) => (
              <div key={label} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
                <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">{label}</p>
                <p className="mono mt-1 text-[13px] text-ink">{value}</p>
              </div>
            ))}
          </div>

          {Array.isArray(features.mfcc_mean) ? (
            <div className="mt-4">
              <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">
                MFCC means (13 coefficients)
              </p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {features.mfcc_mean.map((value, index) => (
                  <span
                    key={index}
                    className="mono rounded-md border border-white/[0.06] bg-white/[0.02] px-1.5 py-1 text-[11px] text-muted"
                    title={`MFCC ${index}`}
                  >
                    {value}
                  </span>
                ))}
              </div>
            </div>
          ) : null}
        </Card>
      ) : null}

      <Card className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-[12px] text-muted">
          <FileText size={15} />
          Reports are generated from this stored record and include the disclaimer.
        </div>
        <div className="flex gap-2">
          {completed ? (
            <Button variant="secondary" size="sm" onClick={downloadReport} loading={downloading}>
              <Download size={14} /> Download PDF
            </Button>
          ) : null}
          <Button variant="secondary" size="sm" onClick={runAnalysis} loading={running}>
            <RefreshCw size={14} /> Re-run analysis
          </Button>
        </div>
      </Card>

      <Modal
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="Delete this analysis?"
        description="The audio file and its stored result will be permanently removed."
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmOpen(false)} disabled={deleting}>
              Cancel
            </Button>
            <Button variant="danger" onClick={deleteAnalysis} loading={deleting}>
              <Trash2 size={14} /> Delete analysis
            </Button>
          </>
        }
      >
        <p className="text-[13px] text-muted">
          {analysis.filename} · {formatDateTime(analysis.created_at)}
        </p>
      </Modal>
    </div>
  )
}
