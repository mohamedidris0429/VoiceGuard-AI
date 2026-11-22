import { useCallback, useEffect, useRef, useState } from 'react'
import { FileAudio, Loader2, Paperclip, Trash2, UploadCloud } from 'lucide-react'
import { audioApi } from '../services/api'
import { formatBytes, formatDuration } from '../utils/format'
import { Alert, Button, EmptyState } from './ui'

export function DropZone({ file, onFileSelected, onClear, disabled, hint, accept = '.wav,.mp3,audio/wav,audio/mpeg' }) {
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)

  const handleFiles = useCallback(
    (fileList) => {
      const next = fileList && fileList[0]
      if (next) onFileSelected(next)
    },
    [onFileSelected],
  )

  const onDrop = (event) => {
    event.preventDefault()
    setDragging(false)
    if (disabled) return
    handleFiles(event.dataTransfer.files)
  }

  if (file) {
    return (
      <div className="rounded-2xl border border-accent/25 bg-accent/[0.04] p-4">
        <div className="flex items-start gap-3">
          <span className="rounded-xl border border-accent/25 bg-accent/10 p-2.5 text-accent">
            <FileAudio size={18} aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-ink">{file.name}</p>
            <p className="mt-0.5 text-xs text-muted">
              {formatBytes(file.size)} · {file.type || 'audio'} · ready for upload
            </p>
          </div>
          {onClear ? (
            <Button variant="ghost" size="sm" onClick={onClear} disabled={disabled} aria-label="Remove file">
              <Trash2 size={14} /> Remove
            </Button>
          ) : null}
        </div>
      </div>
    )
  }

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault()
        if (!disabled) setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={`rounded-2xl border-2 border-dashed p-8 text-center transition ${
        dragging ? 'border-accent bg-accent/[0.06]' : 'border-white/10 bg-white/[0.015]'
      } ${disabled ? 'opacity-60' : ''}`}
    >
      <div className="mx-auto flex max-w-sm flex-col items-center gap-3">
        <span className="rounded-2xl border border-white/10 bg-white/[0.03] p-3 text-accent">
          <UploadCloud size={22} aria-hidden />
        </span>
        <div>
          <p className="text-sm font-semibold text-ink">Drag &amp; drop your recording</p>
          <p className="mt-1 text-xs leading-relaxed text-muted">
            {hint || 'WAV or MP3 · up to 20 MB · 1–60 seconds of audio'}
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={() => inputRef.current?.click()} disabled={disabled}>
          <Paperclip size={14} /> Browse files
        </Button>
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          className="hidden"
          onChange={(event) => {
            handleFiles(event.target.files)
            event.target.value = ''
          }}
          disabled={disabled}
        />
      </div>
    </div>
  )
}

export function AudioPreview({ src, label = 'Audio preview' }) {
  if (!src) return null
  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-[0.08em] text-muted">{label}</p>
      <audio controls src={src} className="w-full" preload="metadata">
        Your browser does not support audio playback.
      </audio>
    </div>
  )
}

export function Waveform({ analysisId, height = 120 }) {
  const canvasRef = useRef(null)
  const [state, setState] = useState({ status: 'loading', peaks: [], duration: 0, error: null })

  useEffect(() => {
    let cancelled = false
    setState({ status: 'loading', peaks: [], duration: 0, error: null })
    audioApi
      .waveform(analysisId, 700)
      .then((data) => {
        if (!cancelled) {
          setState({ status: 'ready', peaks: data.peaks || [], duration: data.duration, error: null })
        }
      })
      .catch((error) => {
        if (!cancelled) setState({ status: 'error', peaks: [], duration: 0, error: error.message })
      })
    return () => {
      cancelled = true
    }
  }, [analysisId])

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas || state.status !== 'ready') return
    const ratio = window.devicePixelRatio || 1
    const width = canvas.clientWidth || 600
    const heightPx = height
    canvas.width = Math.floor(width * ratio)
    canvas.height = Math.floor(heightPx * ratio)
    const context = canvas.getContext('2d')
    context.setTransform(ratio, 0, 0, ratio, 0, 0)
    context.clearRect(0, 0, width, heightPx)

    const peaks = state.peaks
    if (!peaks.length) return

    context.strokeStyle = 'rgba(148, 163, 184, 0.18)'
    context.lineWidth = 1
    context.beginPath()
    context.moveTo(0, heightPx / 2)
    context.lineTo(width, heightPx / 2)
    context.stroke()

    const gradient = context.createLinearGradient(0, 0, width, 0)
    gradient.addColorStop(0, '#14B8A6')
    gradient.addColorStop(0.55, '#22C55E')
    gradient.addColorStop(1, '#4ADE80')
    context.fillStyle = gradient

    const step = width / peaks.length
    const barWidth = Math.max(1, step * 0.62)
    peaks.forEach((peak, index) => {
      const amplitude = Math.max(0.02, peak) * (heightPx / 2 - 3)
      const x = index * step
      context.fillRect(x, heightPx / 2 - amplitude, barWidth, amplitude * 2)
    })
  }, [state, height])

  useEffect(() => {
    draw()
    const onResize = () => draw()
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [draw])

  if (state.status === 'loading') {
    return (
      <div className="flex h-[120px] items-center justify-center rounded-xl border border-white/5 bg-white/[0.02]">
        <Loader2 size={18} className="animate-spin text-teal" aria-hidden />
      </div>
    )
  }

  if (state.status === 'error') {
    return <Alert tone="error">Waveform unavailable: {state.error}</Alert>
  }

  return (
    <div>
      <canvas
        ref={canvasRef}
        style={{ width: '100%', height }}
        className="rounded-xl border border-white/5 bg-[#0B1524]"
        aria-label="Audio waveform"
        role="img"
      />
      <p className="mt-2 text-[11px] text-muted">
        Peak envelope · {formatDuration(state.duration)} · downsampled for display
      </p>
    </div>
  )
}

export function Spectrogram({ analysisId, alt = 'Audio spectrogram' }) {
  const [src, setSrc] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    let objectUrl = null
    setError(null)
    setSrc(null)
    audioApi
      .spectrogramBlob(analysisId)
      .then((blob) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setSrc(objectUrl)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [analysisId])

  if (error) return <Alert tone="error">Spectrogram unavailable: {error}</Alert>

  if (!src) {
    return (
      <div className="flex h-40 items-center justify-center rounded-xl border border-white/5 bg-white/[0.02]">
        <Loader2 size={18} className="animate-spin text-teal" aria-hidden />
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <img src={src} alt={alt} className="w-full rounded-xl border border-white/5" />
      <p className="text-[11px] text-muted">
        Log-mel spectrogram · 96 mel bands · 8 kHz display range
      </p>
    </div>
  )
}

export function FileMeta({ file }) {
  if (!file) return null
  return (
    <dl className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
      {[
        ['Name', file.name],
        ['Size', formatBytes(file.size)],
        ['Type', file.type || 'unknown'],
        ['Source', 'Local file'],
      ].map(([label, value]) => (
        <div key={label} className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-2.5">
          <dt className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">{label}</dt>
          <dd className="mt-1 truncate text-ink" title={String(value)}>
            {value}
          </dd>
        </div>
      ))}
    </dl>
  )
}

export function EmptyAudioState() {
  return (
    <EmptyState
      icon={FileAudio}
      title="No audio selected"
      description="Add a recording to view its waveform, spectrogram and metadata."
    />
  )
}
