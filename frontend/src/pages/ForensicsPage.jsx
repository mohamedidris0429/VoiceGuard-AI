import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Cpu,
  FileAudio,
  Gauge,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Timer,
} from 'lucide-react'
import { forensicsApi } from '../services/api'
import { Spectrogram } from '../components/audio'
import { BandEnergyBars, InteractiveWaveform, RmsTimeline } from '../components/forensics'
import { VerdictPanel } from '../components/verdict'
import { Alert, Badge, Button, Card, EmptyState, PageHeader, Skeleton } from '../components/ui'
import {
  formatBytes,
  formatClock,
  formatDateTime,
  formatDuration,
  formatMs,
  formatPercent,
  statusLabel,
  statusTone,
} from '../utils/format'

const JUMP_SECONDS = 5

function MetaItem({ label, value, mono = false }) {
  return (
    <div className="rounded-xl border border-white/6 bg-white/2 p-3">
      <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">{label}</p>
      <p
        className={`mt-1 truncate text-[13px] font-medium text-ink ${mono ? 'mono' : ''}`}
        title={String(value)}
      >
        {value}
      </p>
    </div>
  )
}

export default function ForensicsPage() {
  const { analysisId } = useParams()
  const navigate = useNavigate()
  const audioRef = useRef(null)

  const [data, setData] = useState(null)
  const [audioUrl, setAudioUrl] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [mediaError, setMediaError] = useState(null)
  const [duration, setDuration] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const payload = await forensicsApi.get(analysisId)
      setData(payload)
      setDuration(payload.waveform.duration || payload.audio.duration_seconds || 0)
    } catch (err) {
      setError(err.message)
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [analysisId])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    let cancelled = false
    let objectUrl = null
    setAudioUrl(null)
    setMediaError(null)
    forensicsApi
      .mediaBlob(analysisId)
      .then((blob) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setAudioUrl(objectUrl)
      })
      .catch((err) => {
        if (!cancelled) setMediaError(err.message)
      })
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [analysisId])

  const seekTo = useCallback(
    (value) => {
      const total = Number.isFinite(duration) && duration > 0 ? duration : 0
      const raw = Number(value) || 0
      const target = Math.max(0, total > 0 ? Math.min(raw, total) : raw)
      setCurrentTime(target)
      if (audioRef.current) {
        try {
          audioRef.current.currentTime = target
        } catch {
          /* the stream may not be ready yet */
        }
      }
    },
    [duration],
  )

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-48" />
        <div className="grid gap-4 lg:grid-cols-3">
          <Skeleton className="h-80 lg:col-span-2" />
          <Skeleton className="h-80" />
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={() => navigate('/history')}>
          <ArrowLeft size={14} /> Back to history
        </Button>
        <Alert
          tone="error"
          title="This recording could not be opened for inspection"
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

  if (!data) {
    return (
      <EmptyState
        icon={FileAudio}
        title="Forensic record not found"
        description="It may have been deleted, or it belongs to another account."
        action={<Button onClick={() => navigate('/history')}>Open history</Button>}
      />
    )
  }

  const audio = data.audio
  const signal = data.signal
  const waveform = data.waveform
  const model = data.model
  const playhead = duration > 0 ? currentTime / duration : 0

  const analysisForVerdict = {
    analysis_status: model.status,
    predicted_class: model.predicted_class,
    model_score: model.model_score,
    failure_reason: model.failure_reason,
    model_details: {
      threshold: model.threshold ?? 0.5,
      windows_analyzed: model.windows_analyzed,
      window_seconds: model.window_seconds,
      aggregation: model.aggregation,
      window_scores: model.window_scores,
    },
  }

  return (
    <div className="animate-fade-in space-y-5">
      <Button variant="ghost" size="sm" onClick={() => navigate(`/analysis/${data.analysis_id}`)}>
        <ArrowLeft size={14} /> Back to analysis record
      </Button>

      <PageHeader
        eyebrow={`Forensics · Analysis #${data.analysis_id}`}
        title={data.filename}
        description={`${(data.file_format || 'audio').toUpperCase()} · ${formatDuration(audio.duration_seconds)} · captured ${formatDateTime(data.created_at)}`}
        actions={
          <>
            <Button variant="secondary" onClick={() => navigate(`/analysis/${data.analysis_id}`)}>
              <ShieldCheck size={15} /> Analysis record
            </Button>
            <Button variant="ghost" onClick={load}>
              <RefreshCw size={14} /> Refresh
            </Button>
          </>
        }
      />

      <Alert tone="warn" title="Signal visualisation — not verified evidence">
        {data.evidence_note}
      </Alert>

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
            <Activity size={15} className="text-teal" /> Recording playback
          </h2>
          <Badge tone="teal">
            {audio.channel_layout} · {audio.sample_rate_hz} Hz
          </Badge>
        </div>

        {mediaError ? (
          <Alert tone="error" className="mt-3" title="Playback unavailable">
            {mediaError}
          </Alert>
        ) : null}

        {audioUrl ? (
          <audio
            ref={audioRef}
            src={audioUrl}
            controls
            preload="metadata"
            className="mt-3 w-full"
            onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
            onLoadedMetadata={(event) => {
              const value = Number(event.currentTarget.duration)
              if (Number.isFinite(value) && value > 0) setDuration(value)
            }}
            onEnded={() => setCurrentTime(duration)}
          >
            Your browser does not support audio playback.
          </audio>
        ) : !mediaError ? (
          <div className="mt-3 flex h-12 items-center justify-center gap-2 text-[12px] text-muted">
            <Loader2 size={16} className="animate-spin" /> Loading audio…
          </div>
        ) : null}

        <div className="mt-3 flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => seekTo(currentTime - JUMP_SECONDS)}
            aria-label={`Back ${JUMP_SECONDS} seconds`}
          >
            <ChevronLeft size={14} /> {JUMP_SECONDS}s
          </Button>
          <input
            type="range"
            min={0}
            max={Math.max(duration, 0.01)}
            step={0.05}
            value={Math.min(currentTime, duration || 0)}
            onChange={(event) => seekTo(event.target.value)}
            aria-label="Timeline position"
            className="h-1.5 flex-1 cursor-pointer rounded-full bg-white/10 accent-[#22C55E]"
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={() => seekTo(currentTime + JUMP_SECONDS)}
            aria-label={`Forward ${JUMP_SECONDS} seconds`}
          >
            {JUMP_SECONDS}s <ChevronRight size={14} />
          </Button>
        </div>
        <div className="mono mt-1 flex justify-between text-[11px] text-muted">
          <span>{formatClock(currentTime)}</span>
          <span>{formatClock(duration)}</span>
        </div>

        <div className="mt-4">
          <InteractiveWaveform
            peaks={waveform.peaks}
            duration={duration || waveform.duration}
            progress={playhead}
            onSeek={seekTo}
          />
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
            <Gauge size={15} className="text-accent" /> Spectrogram and signal energy
          </h2>
          <Spectrogram analysisId={data.analysis_id} />

          <div className="mt-5 grid gap-5 sm:grid-cols-2">
            <div>
              <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
                Loudness over time
              </h3>
              <RmsTimeline times={signal.rms_timeline.times} values={signal.rms_timeline.rms} />
            </div>
            <div>
              <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
                Energy by frequency band
              </h3>
              <BandEnergyBars bands={signal.band_energy} />
            </div>
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <MetaItem label="Spectral centroid" value={`${signal.spectral_centroid_hz ?? '—'} Hz`} mono />
            <MetaItem label="Roll-off (85%)" value={`${signal.spectral_rolloff_hz ?? '—'} Hz`} mono />
            <MetaItem label="Zero-crossing rate" value={signal.zero_crossing_rate ?? '—'} mono />
            <MetaItem label="Peak amplitude" value={signal.peak_amplitude ?? '—'} mono />
            <MetaItem label="Silence ratio" value={formatPercent(signal.silence_ratio ?? 0, 1)} mono />
            <MetaItem label="Analysed window" value={formatDuration(audio.analysed_seconds)} mono />
          </div>

          <p className="mt-3 flex items-start gap-2 text-[11px] leading-relaxed text-muted">
            <AlertTriangle size={13} className="mt-0.5 shrink-0 text-warn" aria-hidden />
            {signal.note}
          </p>
        </Card>

        <div className="space-y-4">
          <Card>
            <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
              <FileAudio size={15} className="text-teal" /> Audio metadata
            </h2>
            <dl className="grid grid-cols-2 gap-3">
              {[
                ['Duration', formatDuration(audio.duration_seconds)],
                ['Sample rate', audio.sample_rate_hz ? `${audio.sample_rate_hz} Hz` : '—'],
                ['Nyquist', audio.nyquist_hz ? `${audio.nyquist_hz} Hz` : '—'],
                ['Channels', audio.channels ?? '—'],
                ['Layout', audio.channel_layout ?? '—'],
                ['Container', (audio.container || '—').toUpperCase()],
                ['Encoding', audio.subtype ?? '—'],
                ['Frames', audio.frames ?? '—'],
                ['File size', formatBytes(audio.file_size_bytes)],
                ['Analysed', formatDuration(audio.analysed_seconds)],
              ].map(([label, value]) => (
                <div key={label} className="rounded-xl border border-white/6 bg-white/2 p-3">
                  <dt className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">
                    {label}
                  </dt>
                  <dd className="mono mt-1 truncate text-[13px] text-ink" title={String(value)}>
                    {value}
                  </dd>
                </div>
              ))}
            </dl>
            {audio.truncated_for_analysis ? (
              <p className="mt-3 text-[11px] leading-relaxed text-muted">
                Signal charts were computed from the first {formatDuration(audio.analysed_seconds)} of
                this recording to keep memory use bounded.
              </p>
            ) : null}
          </Card>

          <Card>
            <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
              <Cpu size={15} className="text-accent" /> Model record
            </h2>
            <div className="space-y-2 text-[12px]">
              <div className="flex items-center justify-between gap-3">
                <span className="text-muted">Status</span>
                <Badge tone={statusTone(model.status)}>{statusLabel(model.status)}</Badge>
              </div>
              {[
                ['Model version', model.model_version || '—'],
                ['Threshold', model.threshold != null ? formatPercent(model.threshold, 0) : '—'],
                ['Windows analysed', model.windows_analyzed ?? '—'],
                ['Window length', model.window_seconds != null ? `${model.window_seconds}s` : '—'],
                ['Aggregation', model.aggregation || '—'],
                ['Inference time', formatMs(model.inference_ms)],
                ['Parameters', model.parameters ? model.parameters.toLocaleString() : '—'],
                ['Device', model.device || '—'],
              ].map(([term, value]) => (
                <div key={term} className="flex items-start justify-between gap-3">
                  <span className="text-muted">{term}</span>
                  <span className="max-w-[60%] break-words text-right font-medium text-ink">
                    {value}
                  </span>
                </div>
              ))}
            </div>
            {model.status !== 'completed' ? (
              <p className="mt-3 flex items-start gap-2 text-[11px] leading-relaxed text-muted">
                <Timer size={13} className="mt-0.5 shrink-0 text-warn" aria-hidden />
                {model.failure_reason ||
                  'No model output is stored for this record yet. Run the analysis from the analysis record page.'}
              </p>
            ) : null}
          </Card>
        </div>
      </div>

      <VerdictPanel analysis={analysisForVerdict} />

      <Alert tone="info" title="How to read this workspace">
        {data.disclaimer}
      </Alert>
    </div>
  )
}
