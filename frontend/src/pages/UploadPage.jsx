import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, ArrowRight, Info, RefreshCw, ShieldCheck, Upload } from 'lucide-react'
import { audioApi } from '../services/api'
import { useToast } from '../context/ToastContext'
import { AudioPreview, DropZone, FileMeta } from '../components/audio'
import { Alert, Button, Card, Field, PageHeader, ProgressBar } from '../components/ui'
import { DISCLAIMER, formatDuration } from '../utils/format'

const ALLOWED_EXTENSIONS = ['wav', 'mp3']
const DEFAULT_LIMITS = { max_upload_mb: 20, min_duration_seconds: 1, max_duration_seconds: 60 }

export default function UploadPage() {
  const navigate = useNavigate()
  const toast = useToast()
  const [limits, setLimits] = useState(DEFAULT_LIMITS)
  const [file, setFile] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [duration, setDuration] = useState(null)
  const [clientError, setClientError] = useState('')
  const [phase, setPhase] = useState('idle') // idle | uploading | analyzing | error
  const [progress, setProgress] = useState(0)
  const [serverError, setServerError] = useState('')
  const [analysisId, setAnalysisId] = useState(null)
  const objectUrlRef = useRef(null)

  useEffect(() => {
    audioApi
      .limits()
      .then((data) => setLimits((current) => ({ ...current, ...data })))
      .catch(() => {})
  }, [])

  useEffect(
    () => () => {
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current)
    },
    [],
  )

  const handleFile = useCallback(
    async (selected) => {
      setClientError('')
      setServerError('')
      setPhase('idle')
      setProgress(0)
      setAnalysisId(null)

      const extension = (selected.name.split('.').pop() || '').toLowerCase()
      if (!ALLOWED_EXTENSIONS.includes(extension)) {
        setClientError('Only .wav and .mp3 files are supported.')
        return
      }
      if (selected.size > limits.max_upload_mb * 1024 * 1024) {
        setClientError(`File is larger than the ${limits.max_upload_mb} MB limit.`)
        return
      }
      if (selected.size === 0) {
        setClientError('That file is empty.')
        return
      }

      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current)
      const url = URL.createObjectURL(selected)
      objectUrlRef.current = url
      setPreviewUrl(url)
      setFile(selected)
      setDuration(null)

      const audio = new Audio()
      audio.preload = 'metadata'
      audio.src = url
      audio.onloadedmetadata = () => {
        const value = Number.isFinite(audio.duration) ? audio.duration : null
        setDuration(value)
        if (value !== null) {
          if (value < limits.min_duration_seconds) {
            setClientError(
              `Recording is too short (${value.toFixed(2)}s). Minimum is ${limits.min_duration_seconds}s.`,
            )
          } else if (value > limits.max_duration_seconds) {
            setClientError(
              `Recording is too long (${value.toFixed(1)}s). Maximum is ${limits.max_duration_seconds}s.`,
            )
          }
        }
      }
      audio.onerror = () => setClientError('This file could not be read as audio by the browser.')
    },
    [limits],
  )

  const clearFile = () => {
    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current)
    objectUrlRef.current = null
    setPreviewUrl(null)
    setFile(null)
    setDuration(null)
    setClientError('')
    setServerError('')
    setPhase('idle')
    setProgress(0)
    setAnalysisId(null)
  }

  const runAnalysis = async (id) => {
    setPhase('analyzing')
    setServerError('')
    try {
      const result = await audioApi.analyze(id)
      if (result.analysis_status === 'completed') {
        toast.success('Analysis complete — opening the result.')
        navigate(`/analysis/${result.id}`)
        return
      }
      setPhase('error')
      setServerError(
        result.failure_reason ||
          'The model could not analyse this recording. Check the system status page for details.',
      )
      toast.error('The analysis did not produce a result.')
    } catch (error) {
      setPhase('error')
      setServerError(error.message)
      toast.error(error.message)
    }
  }

  const submit = async () => {
    if (!file || clientError) return
    setPhase('uploading')
    setProgress(0)
    setServerError('')
    try {
      const uploaded = await audioApi.upload(file, setProgress)
      setAnalysisId(uploaded.id)
      await runAnalysis(uploaded.id)
    } catch (error) {
      setPhase('error')
      setServerError(error.message)
      toast.error(error.message)
    }
  }

  const busy = phase === 'uploading' || phase === 'analyzing'

  return (
    <div className="animate-fade-in">
      <PageHeader
        eyebrow="New analysis"
        title="Analyse a recording"
        description="Upload a WAV or MP3 file. The audio is validated, converted to the model's 16 kHz mono format and scored by the pretrained spoof detector."
      />

      <div className="grid gap-5 lg:grid-cols-[1.6fr_1fr]">
        <div className="space-y-4">
          <Card>
            <DropZone
              file={file}
              onFileSelected={handleFile}
              onClear={busy ? undefined : clearFile}
              disabled={busy}
              hint={`WAV or MP3 · up to ${limits.max_upload_mb} MB · ${limits.min_duration_seconds}–${limits.max_duration_seconds} seconds`}
            />

            {clientError ? (
              <Alert tone="error" className="mt-3" title="That file cannot be used">
                {clientError}
              </Alert>
            ) : null}

            {file ? (
              <div className="mt-4 space-y-4">
                <FileMeta file={file} />
                {duration !== null ? (
                  <p className="text-xs text-muted">
                    Decoded duration: <span className="font-semibold text-ink">{formatDuration(duration)}</span>
                  </p>
                ) : null}
                <AudioPreview src={previewUrl} label="Preview before analysis" />
              </div>
            ) : null}

            {busy || phase === 'error' ? (
              <div className="mt-5 space-y-2 rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
                <div className="flex items-center justify-between text-[12px]">
                  <span className="font-medium text-ink">
                    {phase === 'uploading'
                      ? 'Uploading securely…'
                      : phase === 'analyzing'
                        ? 'Running AI inference on CPU…'
                        : 'Analysis interrupted'}
                  </span>
                  {phase === 'uploading' ? (
                    <span className="mono text-muted">{progress}%</span>
                  ) : phase === 'analyzing' ? (
                    <span className="text-teal">model working…</span>
                  ) : null}
                </div>
                <ProgressBar
                  value={phase === 'uploading' ? progress : phase === 'analyzing' ? 100 : 100}
                  tone={phase === 'error' ? 'danger' : phase === 'analyzing' ? 'teal' : 'accent'}
                />
                {phase === 'analyzing' ? (
                  <p className="text-[11px] leading-relaxed text-muted">
                    Short recordings usually finish in a few seconds. The model is loaded once and
                    reused for later analyses.
                  </p>
                ) : null}
              </div>
            ) : null}

            {serverError ? (
              <Alert tone="error" className="mt-4" title="Analysis failed">
                {serverError}
              </Alert>
            ) : null}

            <div className="mt-5 flex flex-wrap items-center gap-2">
              <Button onClick={submit} disabled={!file || Boolean(clientError) || busy} loading={busy}>
                <ShieldCheck size={16} />
                {busy ? 'Analysing…' : 'Analyse recording'}
              </Button>
              {phase === 'error' && analysisId ? (
                <Button variant="secondary" onClick={() => runAnalysis(analysisId)}>
                  <RefreshCw size={14} /> Retry analysis
                </Button>
              ) : null}
              {file && !busy ? (
                <Button variant="ghost" onClick={clearFile}>
                  Clear
                </Button>
              ) : null}
            </div>
          </Card>

          <Alert tone="info" title="What happens after upload">
            <ol className="ml-4 list-decimal space-y-1">
              <li>The file container and header are validated — the extension alone is not trusted.</li>
              <li>Audio is decoded to mono 16 kHz and split into bounded windows.</li>
              <li>The pretrained classifier scores each window; scores are averaged.</li>
              <li>The record, metadata and features are stored in PostgreSQL for your account.</li>
            </ol>
          </Alert>
        </div>

        <div className="space-y-4">
          <Card>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
              <Info size={15} className="text-teal" /> Accepted input
            </h2>
            <dl className="mt-3 space-y-2.5 text-[13px]">
              {[
                ['Formats', 'WAV, MP3'],
                ['Maximum size', `${limits.max_upload_mb} MB`],
                ['Duration', `${limits.min_duration_seconds}s – ${limits.max_duration_seconds}s`],
                ['Sample rate', '8 kHz and above (converted to 16 kHz)'],
                ['Channels', 'Mono or stereo (mixed to mono)'],
                ['Processing', 'CPU only, no GPU required'],
              ].map(([term, value]) => (
                <div key={term} className="flex items-start justify-between gap-3">
                  <dt className="text-muted">{term}</dt>
                  <dd className="text-right font-medium text-ink">{value}</dd>
                </div>
              ))}
            </dl>
          </Card>

          <Card className="border-warn/20 bg-warn/[0.03]">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-warn">
              <AlertTriangle size={15} /> Limitations
            </h2>
            <p className="mt-2 text-[12px] leading-relaxed text-muted">
              {DISCLAIMER} Heavily compressed audio, music, background noise or multiple speakers
              reduce reliability. The verdict is about the signal, not about who is speaking.
            </p>
          </Card>

          <Button variant="secondary" className="w-full" onClick={() => navigate('/record')}>
            Record with microphone instead <ArrowRight size={14} />
          </Button>
        </div>
      </div>
    </div>
  )
}
