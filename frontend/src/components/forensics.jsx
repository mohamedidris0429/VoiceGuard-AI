import { useCallback, useEffect, useRef } from 'react'

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value))
}

/**
 * Canvas peak envelope with click / keyboard seeking.
 * Purely visual: the drawing is skipped when a canvas 2D context is unavailable
 * (for example under jsdom), so the component stays safe to render in tests.
 */
export function InteractiveWaveform({
  peaks = [],
  duration = 0,
  progress = 0,
  onSeek,
  height = 128,
  label = 'Interactive audio waveform',
}) {
  const canvasRef = useRef(null)

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const context = typeof canvas.getContext === 'function' ? canvas.getContext('2d') : null
    if (!context) return

    const ratio = window.devicePixelRatio || 1
    const width = canvas.clientWidth || 600
    canvas.width = Math.floor(width * ratio)
    canvas.height = Math.floor(height * ratio)
    context.setTransform(ratio, 0, 0, ratio, 0, 0)
    context.clearRect(0, 0, width, height)

    context.strokeStyle = 'rgba(148, 163, 184, 0.18)'
    context.lineWidth = 1
    context.beginPath()
    context.moveTo(0, height / 2)
    context.lineTo(width, height / 2)
    context.stroke()

    if (peaks.length) {
      const gradient = context.createLinearGradient(0, 0, width, 0)
      gradient.addColorStop(0, '#14B8A6')
      gradient.addColorStop(0.55, '#22C55E')
      gradient.addColorStop(1, '#4ADE80')
      context.fillStyle = gradient

      const step = width / peaks.length
      const barWidth = Math.max(1, step * 0.62)
      peaks.forEach((peak, index) => {
        const amplitude = Math.max(0.02, Number(peak) || 0) * (height / 2 - 3)
        context.fillRect(index * step, height / 2 - amplitude, barWidth, amplitude * 2)
      })
    }

    const playhead = clamp(progress, 0, 1)
    if (playhead > 0) {
      const x = playhead * width
      context.fillStyle = 'rgba(34, 197, 94, 0.10)'
      context.fillRect(0, 0, x, height)
      context.strokeStyle = '#4ADE80'
      context.lineWidth = 1.5
      context.beginPath()
      context.moveTo(x, 0)
      context.lineTo(x, height)
      context.stroke()
    }
  }, [peaks, height, progress])

  useEffect(() => {
    draw()
    const onResize = () => draw()
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [draw])

  const seekFromMouse = (event) => {
    if (!onSeek || !duration) return
    const rect = event.currentTarget.getBoundingClientRect()
    const ratio = clamp((event.clientX - rect.left) / Math.max(1, rect.width), 0, 1)
    onSeek(ratio * duration)
  }

  return (
    <div>
      <canvas
        ref={canvasRef}
        role="img"
        aria-label={label}
        tabIndex={0}
        onClick={seekFromMouse}
        onKeyDown={(event) => {
          if (!onSeek || !duration) return
          if (event.key === 'ArrowRight') onSeek(clamp(progress + 0.02, 0, 1) * duration)
          if (event.key === 'ArrowLeft') onSeek(clamp(progress - 0.02, 0, 1) * duration)
        }}
        style={{ width: '100%', height }}
        className="cursor-crosshair rounded-xl border border-white/5 bg-[#0B1524] focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
      />
      <p className="mt-2 text-[11px] text-muted">
        Peak envelope · click the waveform or use the arrow keys to jump in the timeline
      </p>
    </div>
  )
}

/** Loudness envelope as a lightweight inline SVG (no chart library needed). */
export function RmsTimeline({ times = [], values = [], height = 120 }) {
  if (!values.length) {
    return <p className="text-[12px] text-muted">No RMS timeline available for this recording.</p>
  }

  const width = 600
  const peak = Math.max(...values.map((value) => Number(value) || 0), 0.0001)
  const points = values.map((value, index) => {
    const x = values.length === 1 ? 0 : (index / (values.length - 1)) * width
    const y = height - ((Number(value) || 0) / peak) * (height - 8) - 4
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  const area = `0,${height} ${points.join(' ')} ${width},${height}`
  const first = times.length ? Number(times[0]).toFixed(2) : null
  const last = times.length ? Number(times[times.length - 1]).toFixed(2) : null

  return (
    <div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        role="img"
        aria-label="RMS energy over time"
        className="h-32 w-full rounded-xl border border-white/5 bg-[#0B1524]"
      >
        <polygon points={area} fill="rgba(20, 184, 166, 0.18)" />
        <polyline points={points.join(' ')} fill="none" stroke="#14B8A6" strokeWidth="1.5" />
      </svg>
      <p className="mt-2 text-[11px] text-muted">
        Frame RMS energy · {values.length} points
        {first !== null ? ` · ${first}s–${last}s` : ''}
      </p>
    </div>
  )
}

/** Relative energy per fixed frequency band. */
export function BandEnergyBars({ bands = [] }) {
  if (!bands.length) {
    return <p className="text-[12px] text-muted">No frequency band data for this recording.</p>
  }

  const peak = Math.max(...bands.map((band) => Number(band.share) || 0), 0.0001)

  return (
    <div className="space-y-2.5" role="img" aria-label="Relative energy by frequency band">
      {bands.map((band) => {
        const share = Number(band.share) || 0
        return (
          <div key={band.label} className="space-y-1">
            <div className="flex items-center justify-between text-[11px]">
              <span className="text-muted">{band.label}</span>
              <span className="mono font-semibold text-ink">{(share * 100).toFixed(1)}%</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
              <div
                className="h-full rounded-full bg-gradient-to-r from-teal to-accent"
                style={{ width: `${Math.max(2, (share / peak) * 100)}%` }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}
