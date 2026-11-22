import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, Info, Mic, RotateCcw, ShieldCheck, Square } from 'lucide-react'
import { audioApi } from '../services/api'
import { useToast } from '../context/ToastContext'
import { AudioPreview } from '../components/audio'
import { Alert, Button, Card, PageHeader, ProgressBar } from '../components/ui'
import { formatClock, formatDuration } from '../utils/format'
import { recordingToWavBlob, wavFileName } from '../utils/wav'

const MAX_SECONDS = 60

function pickMimeType() {
  if (typeof MediaRecorder === 'undefined') return ''
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']
  return candidates.find((type) => MediaRecorder.isTypeSupported(type)) || ''
}

export default function RecordPage() {
  const navigate = useNavigate()
  const toast = useToast()
  const [supported] = useState(
    typeof navigator !== 'undefined' &&
      Boolean(navigator.mediaDevices?.getUserMedia) &&
      typeof MediaRecorder !== 'undefined',
  )
  const [recording, setRecording] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [permission, setPermission] = useState('idle') // idle | granted | denied
  const [wavFile, setWavFile] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [duration, setDuration] = useState(0)
  const [error, setError] = useState('')
  const [phase, setPhase] = useState('idle') // idle | preparing | uploading | analyzing | error
  const [progress, setProgress] = useState(0)

  const streamRef = useRef(null)
  const recorderRef = useRef(null)
  const chunksRef = useRef([])
  const timerRef = useRef(null)
  const urlRef = useRef(null)

  const stopTracks = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }
  }

  const clearTimer = () => {
    if (timerRef.current) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
  }

  useEffect(
    () => () => {
      clearTimer()
      stopTracks()
      if (urlRef.current) URL.revokeObjectURL(urlRef.current)
    },
    [],
  )

  const setPreview = (blob) => {
    if (urlRef.current) URL.revokeObjectURL(urlRef.current)
    const url = URL.createObjectURL(blob)
    urlRef.current = url
    setPreviewUrl(url)
  }

  const startRecording = async () => {
    setError('')
    setPhase('idle')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      setPermission('granted')

      const mimeType = pickMimeType()
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream)
      chunksRef.current = []

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) chunksRef.current.push(event.data)
      }
      recorder.onstop = async () => {
        clearTimer()
        stopTracks()
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' })
        chunksRef.current = []
        if (blob.size === 0) {
          setError('No audio was captured. Check your microphone and try again.')
          setPhase('error')
          return
        }
        setPhase('preparing')
        try {
          const wavBlob = await recordingToWavBlob(blob)
          const file = new File([wavBlob], wavFileName(), { type: 'audio/wav' })
          setWavFile(file)
          setPreview(wavBlob)
          setPhase('idle')
          toast.success('Recording captured. Listen back, then run the analysis.')
        } catch (conversionError) {
          setError(
            'The recording could not be converted for analysis in this browser. Try uploading a WAV file instead.',
          )
          setPhase('error')
        }
      }

      recorder.onerror = () => {
        setError('The recorder stopped unexpectedly. Please try again.')
        setPhase('error')
        setRecording(false)
        clearTimer()
      }

      recorderRef.current = recorder
      recorder.start(250)
      setRecording(true)
      setDuration(0)
      setElapsed(0)
      const startedAt = Date.now()
      timerRef.current = window.setInterval(() => {
        const seconds = (Date.now() - startedAt) / 1000
        setElapsed(seconds)
        if (seconds >= MAX_SECONDS) {
          recorder.stop()
          setRecording(false)
          setDuration(MAX_SECONDS)
        }
      }, 200)
    } catch (permissionError) {
      stopTracks()
      if (permissionError?.name === 'NotAllowedError' || permissionError?.name === 'SecurityError') {
        setPermission('denied')
        setError('Microphone access was denied. Allow microphone permission in the browser and try again.')
      } else if (permissionError?.name === 'NotFoundError') {
        setError('No microphone was found on this device.')
      } else {
        setError('The microphone could not be started on this device.')
      }
      setPhase('error')
    }
  }

  const stopRecording = () => {
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      recorderRef.current.stop()
    }
    setRecording(false)
    setDuration(elapsed || 0)
  }

  const reset = () => {
    setWavFile(null)
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current)
      urlRef.current = null
    }
    setPreviewUrl(null)
    setDuration(0)
    setElapsed(0)
    setError('')
    setPhase('idle')
    setProgress(0)
  }

  const submit = async () => {
    if (!wavFile) return
    setError('')
    setPhase('uploading')
    setProgress(0)
    try {
      const uploaded = await audioApi.upload(wavFile, setProgress)
      setPhase('analyzing')
      const result = await audioApi.analyze(uploaded.id)
      if (result.analysis_status === 'completed') {
        toast.success('Recording analysed.')
        navigate(`/analysis/${result.id}`)
        return
      }
      setPhase('error')
      setError(result.failure_reason || 'The model could not analyse this recording.')
    } catch (uploadError) {
      setPhase('error')
      setError(uploadError.message)
      toast.error(uploadError.message)
    }
  }

  const busy = phase === 'uploading' || phase === 'analyzing' || phase === 'preparing'

  return (
    <div className="animate-fade-in">
      <PageHeader
        eyebrow="Microphone"
        title="Record and analyse your voice"
        description="Capture up to 60 seconds with the browser MediaRecorder API. The clip is converted to WAV in your browser and then analysed through the same backend pipeline as an upload."
      />

      <div className="grid gap-5 lg:grid-cols-[1.6fr_1fr]">
        <Card className="space-y-5">
          {!supported ? (
            <Alert tone="error" title="Recording is not supported in this browser">
              This browser does not expose the MediaRecorder API. Use a current version of Chrome,
              Edge or Firefox, or upload a WAV/MP3 file instead.
            </Alert>
          ) : null}

          <div className="flex flex-col items-center gap-4 rounded-2xl border border-white/[0.06] bg-[#0B1524]/60 p-8">
            <div
              className={`flex h-24 w-24 items-center justify-center rounded-full border-2 transition ${
                recording
                  ? 'animate-pulse-soft border-danger/60 bg-danger/10 text-danger'
                  : 'border-accent/30 bg-accent/[0.07] text-accent'
              }`}
            >
              <Mic size={34} aria-hidden />
            </div>

            <div className="text-center">
              <p className="mono text-3xl font-semibold tracking-tight text-ink">
                {formatClock(recording ? elapsed : duration)}
              </p>
              <p className="mt-1 text-[12px] text-muted">
                {recording
                  ? 'Recording… speak clearly, up to 60 seconds'
                  : wavFile
                    ? 'Recording ready for analysis'
                    : 'Press start and allow microphone access'}
              </p>
            </div>

            <div className="flex flex-wrap justify-center gap-2">
              {!recording ? (
                <Button onClick={startRecording} disabled={!supported || busy || Boolean(wavFile)}>
                  <Mic size={15} /> {wavFile ? 'Recording captured' : 'Start recording'}
                </Button>
              ) : (
                <Button variant="danger" onClick={stopRecording}>
                  <Square size={14} /> Stop recording
                </Button>
              )}
              {wavFile && !busy ? (
                <Button variant="ghost" onClick={reset}>
                  <RotateCcw size={14} /> Re-record
                </Button>
              ) : null}
            </div>

            {wavFile ? (
              <p className="text-[11px] text-muted">
                Captured {formatDuration(duration)} · encoded as 16-bit mono WAV ·{' '}
                {(wavFile.size / 1024).toFixed(0)} KB
              </p>
            ) : null}
          </div>

          {previewUrl ? <AudioPreview src={previewUrl} label="Playback" /> : null}

          {error ? (
            <Alert tone={permission === 'denied' ? 'warn' : 'error'} title="Recording problem">
              {error}
            </Alert>
          ) : null}

          {busy ? (
            <div className="space-y-2">
              <p className="text-[12px] text-muted">
                {phase === 'preparing'
                  ? 'Converting the recording to WAV…'
                  : phase === 'uploading'
                    ? 'Uploading the recording…'
                    : 'Running AI inference on CPU…'}
              </p>
              <ProgressBar
                value={phase === 'uploading' ? progress : 100}
                tone={phase === 'analyzing' ? 'teal' : 'accent'}
                showLabel={phase === 'uploading'}
              />
            </div>
          ) : null}

          <div className="flex flex-wrap gap-2">
            <Button onClick={submit} disabled={!wavFile || busy} loading={busy}>
              <ShieldCheck size={16} /> Analyse recording
            </Button>
            {wavFile ? (
              <Button
                variant="secondary"
                onClick={() => {
                  const url = URL.createObjectURL(wavFile)
                  const anchor = document.createElement('a')
                  anchor.href = url
                  anchor.download = wavFile.name
                  anchor.click()
                  setTimeout(() => URL.revokeObjectURL(url), 3000)
                }}
              >
                Download WAV
              </Button>
            ) : null}
          </div>
        </Card>

        <div className="space-y-4">
          <Card>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
              <Info size={15} className="text-teal" /> How this works
            </h2>
            <ul className="mt-2 space-y-2 text-[12px] leading-relaxed text-muted">
              <li>• Your browser asks for microphone permission only when you press start.</li>
              <li>• Audio stays on your device until you press “Analyse recording”.</li>
              <li>• The clip is analysed after you stop — this is not continuous live monitoring.</li>
              <li>• Recordings are stored against your account and can be deleted at any time.</li>
            </ul>
          </Card>

          <Card className="border-warn/20 bg-warn/[0.03]">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-warn">
              <AlertTriangle size={15} /> Before you record
            </h2>
            <p className="mt-2 text-[12px] leading-relaxed text-muted">
              Record in a quiet room with a single speaker close to the microphone. Background
              speech, music and heavy processing lower confidence. Any result is an indicator, not
              proof of identity.
            </p>
          </Card>

          <Button variant="secondary" className="w-full" onClick={() => navigate('/upload')}>
            Upload a file instead
          </Button>
        </div>
      </div>
    </div>
  )
}
