import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Activity,
  AlertTriangle,
  Info,
  Mic,
  Radio,
  ShieldCheck,
  Square,
  Trash2,
} from 'lucide-react'
import { streamApi } from '../services/api'
import { useToast } from '../context/ToastContext'
import { Alert, Badge, Button, Card, EmptyState, PageHeader, ProgressBar } from '../components/ui'
import { formatPercent } from '../utils/format'
import { recordingToWavBlob } from '../utils/wav'

const CHUNK_SECONDS = 3
const MAX_SECONDS = 60

function pickMimeType() {
  if (typeof MediaRecorder === 'undefined') return ''
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']
  return candidates.find((type) => MediaRecorder.isTypeSupported(type)) || ''
}

function scoreTone(score) {
  if (score == null) return 'bg-white/10'
  if (score >= 0.5) return 'bg-danger'
  if (score >= 0.3) return 'bg-warn'
  return 'bg-accent'
}

export default function LivePage() {
  const navigate = useNavigate()
  const toast = useToast()

  const [supported] = useState(
    typeof navigator !== 'undefined' &&
      Boolean(navigator.mediaDevices?.getUserMedia) &&
      typeof MediaRecorder !== 'undefined',
  )
  const [session, setSession] = useState(null)
  const [status, setStatus] = useState('idle') // idle | starting | capturing | scoring | stopping | stopped
  const [elapsed, setElapsed] = useState(0)
  const [error, setError] = useState('')
  const [permission, setPermission] = useState('idle')

  const goingRef = useRef(false)
  const streamRef = useRef(null)
  const recorderRef = useRef(null)
  const resolveClipRef = useRef(null)
  const timerRef = useRef(null)
  const sessionRef = useRef(null)
  const elapsedRef = useRef(0)

  const releaseStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }
    if (timerRef.current) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  useEffect(
    () => () => {
      goingRef.current = false
      if (recorderRef.current && recorderRef.current.state !== 'inactive') {
        try {
          recorderRef.current.stop()
        } catch {
          /* already stopped */
        }
      }
      releaseStream()
      if (sessionRef.current) {
        streamApi.discard(sessionRef.current).catch(() => {})
      }
    },
    [releaseStream],
  )

  const recordClip = (stream) =>
    new Promise((resolve, reject) => {
      let recorder
      try {
        const mimeType = pickMimeType()
        recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream)
      } catch (error) {
        reject(error)
        return
      }
      const chunks = []
      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) chunks.push(event.data)
      }
      recorder.onerror = () => reject(new Error('The microphone recorder stopped unexpectedly.'))
      recorder.onstop = () => {
        resolveClipRef.current = null
        const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' })
        resolve(blob.size > 0 ? blob : null)
      }
      recorderRef.current = recorder
      resolveClipRef.current = () => {
        if (recorder.state !== 'inactive') recorder.stop()
      }
      recorder.start()
      window.setTimeout(() => {
        if (recorder.state !== 'inactive') recorder.stop()
      }, CHUNK_SECONDS * 1000)
    })

  const finishSession = useCallback(async () => {
    goingRef.current = false
    releaseStream()
    const id = sessionRef.current
    if (!id) {
      setStatus('stopped')
      return
    }
    setStatus('stopping')
    try {
      const summary = await streamApi.stop(id)
      setSession(summary)
    } catch (err) {
      setError(err.message)
    } finally {
      setStatus('stopped')
      sessionRef.current = null
    }
  }, [releaseStream])

  const captureLoop = useCallback(
    async (stream, sessionId) => {
      let index = 0
      while (goingRef.current && elapsedRef.current < MAX_SECONDS) {
        setStatus('capturing')
        let blob
        try {
          blob = await recordClip(stream)
        } catch (err) {
          setError(err.message)
          break
        }
        if (!blob || !goingRef.current) break
        if (elapsedRef.current >= MAX_SECONDS) break

        setStatus('scoring')
        try {
          const wavBlob = await recordingToWavBlob(blob)
          const updated = await streamApi.sendChunk(sessionId, wavBlob, index)
          setSession(updated)
          index += 1
        } catch (err) {
          setError(err.message)
          break
        }
        if (elapsedRef.current >= MAX_SECONDS) break
      }
      await finishSession()
    },
    [finishSession],
  )

  const start = async () => {
    setError('')
    setSession(null)
    setElapsed(0)
    elapsedRef.current = 0
    setStatus('starting')
    let createdId = null
    try {
      const created = await streamApi.create(CHUNK_SECONDS)
      createdId = created.session_id
      sessionRef.current = created.session_id
      setSession(created)

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      })
      streamRef.current = stream
      setPermission('granted')

      goingRef.current = true
      const startedAt = Date.now()
      timerRef.current = window.setInterval(() => {
        elapsedRef.current = (Date.now() - startedAt) / 1000
        setElapsed(elapsedRef.current)
        if (elapsedRef.current >= MAX_SECONDS) {
          goingRef.current = false
          resolveClipRef.current?.()
        }
      }, 200)

      captureLoop(stream, created.session_id)
    } catch (err) {
      goingRef.current = false
      releaseStream()
      sessionRef.current = null
      if (err?.name === 'NotAllowedError' || err?.name === 'SecurityError') {
        setPermission('denied')
        setError('Microphone access was denied. Allow the permission in your browser and try again.')
      } else if (err?.name === 'NotFoundError') {
        setError('No microphone was found on this device.')
      } else {
        setError(err.message || 'The live session could not be started.')
      }
      setStatus('idle')
      if (createdId) streamApi.discard(createdId).catch(() => {})
    }
  }

  const stop = () => {
    goingRef.current = false
    resolveClipRef.current?.()
    setStatus('stopping')
  }

  const discard = async () => {
    const id = sessionRef.current || session?.session_id
    goingRef.current = false
    resolveClipRef.current?.()
    releaseStream()
    if (id) {
      try {
        await streamApi.discard(id)
      } catch {
        /* best effort */
      }
    }
    sessionRef.current = null
    setSession(null)
    setElapsed(0)
    elapsedRef.current = 0
    setStatus('idle')
    toast.success('Live session discarded. No audio was retained.')
  }

  const chunks = session?.chunks || []
  const active = ['starting', 'capturing', 'scoring', 'stopping'].includes(status)
  const average = session?.average_score

  return (
    <div className="animate-fade-in">
      <PageHeader
        eyebrow="Live analysis"
        title="Near-real-time voice monitor"
        description={`Records ${CHUNK_SECONDS}-second clips and scores each one with the same pretrained detector. This is chunked near-real-time analysis, not continuous or instantaneous detection.`}
        actions={
          active ? (
            <Button variant="danger" onClick={stop}>
              <Square size={14} /> Stop session
            </Button>
          ) : (
            <Button onClick={start} disabled={!supported}>
              <Mic size={15} /> Start session
            </Button>
          )
        }
      />

      <div className="grid gap-5 lg:grid-cols-[1.6fr_1fr]">
        <div className="space-y-4">
          <Card>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <span
                  className={`flex h-12 w-12 items-center justify-center rounded-2xl border ${
                    active
                      ? 'animate-pulse-soft border-danger/50 bg-danger/10 text-danger'
                      : 'border-accent/25 bg-accent/10 text-accent'
                  }`}
                >
                  <Radio size={20} aria-hidden />
                </span>
                <div>
                  <p className="mono text-2xl font-semibold text-ink">
                    {String(Math.floor(elapsed / 60)).padStart(2, '0')}:
                    {String(Math.floor(elapsed % 60)).padStart(2, '0')}
                  </p>
                  <p className="text-[12px] text-muted">
                    {status === 'idle' && 'Ready to record'}
                    {status === 'starting' && 'Starting…'}
                    {status === 'capturing' && `Capturing a ${CHUNK_SECONDS}s clip…`}
                    {status === 'scoring' && 'Scoring the clip on CPU…'}
                    {status === 'stopping' && 'Closing the session…'}
                    {status === 'stopped' && 'Session ended'}
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={active ? 'danger' : status === 'stopped' ? 'neutral' : 'teal'}>
                  {active ? 'Live' : status === 'stopped' ? 'Stopped' : 'Idle'}
                </Badge>
                <Badge tone="neutral">{CHUNK_SECONDS}s chunks</Badge>
                <Badge tone="neutral">Up to {MAX_SECONDS}s</Badge>
              </div>
            </div>

            <div className="mt-4">
              <ProgressBar value={(Math.min(elapsed, MAX_SECONDS) / MAX_SECONDS) * 100} />
            </div>

            {error ? (
              <Alert
                tone={permission === 'denied' ? 'warn' : 'error'}
                className="mt-4"
                title="Live session problem"
              >
                {error}
              </Alert>
            ) : null}

            {!supported ? (
              <Alert tone="error" className="mt-4" title="Recording is not supported here">
                This browser does not expose MediaRecorder/getUserMedia. Use a current Chrome, Edge
                or Firefox build, or analyse an uploaded file instead.
              </Alert>
            ) : null}

            <div className="mt-5">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
                  Chunk timeline
                </p>
                <p className="text-[11px] text-muted">
                  {chunks.length} scored · average{' '}
                  <span className="mono text-ink">
                    {average != null ? formatPercent(average) : '—'}
                  </span>
                </p>
              </div>

              {chunks.length === 0 ? (
                <EmptyState
                  icon={Activity}
                  title={active ? 'Waiting for the first clip' : 'No live chunks yet'}
                  description={
                    active
                      ? 'Each clip appears here as soon as the model finishes scoring it.'
                      : 'Start a session to see per-chunk synthetic-speech probabilities appear.'
                  }
                />
              ) : (
                <div className="space-y-2">
                  <div className="flex h-16 items-end gap-1">
                    {chunks.map((chunk) => (
                      <div
                        key={chunk.index}
                        className="group relative flex-1 rounded-t"
                        style={{ height: `${Math.max(6, chunk.score * 100)}%` }}
                        title={`Chunk ${chunk.index + 1} · ${formatPercent(chunk.score)} · ${chunk.label}`}
                      >
                        <div className={`h-full w-full rounded-t ${scoreTone(chunk.score)}`} />
                      </div>
                    ))}
                  </div>
                  <div className="flex justify-between text-[10px] text-muted">
                    <span>0 s</span>
                    <span>threshold 50%</span>
                    <span>
                      {chunks.length
                        ? `${chunks[chunks.length - 1].end_seconds.toFixed(1)} s`
                        : '0 s'}
                    </span>
                  </div>
                </div>
              )}
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {!active && status !== 'idle' ? (
                <Button variant="secondary" onClick={start}>
                  <Mic size={14} /> New session
                </Button>
              ) : null}
              {chunks.length > 0 || active ? (
                <Button variant="ghost" onClick={discard}>
                  <Trash2 size={14} /> Discard session
                </Button>
              ) : null}
              {status === 'stopped' && average != null ? (
                <Button variant="secondary" onClick={() => navigate('/history')}>
                  Open analysis history
                </Button>
              ) : null}
            </div>
          </Card>

          {session ? (
            <Card>
              <h2 className="mb-2 text-sm font-semibold text-ink">Per-chunk results</h2>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[520px] text-[13px]">
                  <thead>
                    <tr className="text-left text-[10px] uppercase tracking-[0.08em] text-muted">
                      <th className="px-2 py-2">#</th>
                      <th className="px-2 py-2">Window</th>
                      <th className="px-2 py-2">Score</th>
                      <th className="px-2 py-2">Label</th>
                      <th className="px-2 py-2">Latency</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {chunks.map((chunk) => (
                      <tr key={chunk.index}>
                        <td className="mono px-2 py-2 text-muted">{chunk.index + 1}</td>
                        <td className="mono px-2 py-2 text-muted">
                          {chunk.start_seconds.toFixed(1)}–{chunk.end_seconds.toFixed(1)}s
                        </td>
                        <td className="mono px-2 py-2 text-ink">{formatPercent(chunk.score)}</td>
                        <td className="px-2 py-2">
                          <Badge tone={chunk.label === 'synthetic' ? 'danger' : 'success'}>
                            {chunk.label}
                          </Badge>
                        </td>
                        <td className="mono px-2 py-2 text-muted">{chunk.latency_ms} ms</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-3 flex items-start gap-2 text-[11px] leading-relaxed text-muted">
                <Info size={13} className="mt-0.5 shrink-0" />
                {session.window_note}
              </p>
            </Card>
          ) : null}
        </div>

        <div className="space-y-4">
          <Alert tone="warn" title="What “near-real-time” means here">
            {session?.latency_note ||
              'Each clip is scored after it is captured; latency is at least the clip length plus inference time, with a short gap while the next clip is finalised.'}
          </Alert>

          <Card>
            <h2 className="text-sm font-semibold text-ink">Privacy</h2>
            <ul className="mt-2 space-y-2 text-[12px] leading-relaxed text-muted">
              <li>• The microphone is opened only when you press start, and the browser prompts first.</li>
              <li>• Only the current clip is uploaded, and the server deletes it after scoring.</li>
              <li>• Live results are held in memory for the session and are never written to the database.</li>
              <li>• No recording is kept; discard the session to drop it immediately.</li>
            </ul>
          </Card>

          <Card className="border-warn/20 bg-warn/[0.03]">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-warn">
              <AlertTriangle size={15} /> Limitations
            </h2>
            <p className="mt-2 text-[12px] leading-relaxed text-muted">
              {session?.caveat ||
                'Chunk scores are independent model outputs for short windows. The running average is not a verified whole-file verdict and must not be presented as one.'}
            </p>
          </Card>

          <Card>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
              <ShieldCheck size={15} className="text-teal" /> For a permanent record
            </h2>
            <p className="mt-2 text-[12px] leading-relaxed text-muted">
              Live sessions are ephemeral. To store an analysis, download your recording from the
              record page or upload it, then run a full-file analysis with a PDF report.
            </p>
            <Button variant="secondary" size="sm" className="mt-3" onClick={() => navigate('/record')}>
              Open recorder
            </Button>
          </Card>
        </div>
      </div>
    </div>
  )
}
