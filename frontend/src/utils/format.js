export function formatDateTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString(undefined, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' })
}

export function formatDuration(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return '—'
  const value = Number(seconds)
  if (value < 60) return `${value.toFixed(value < 10 ? 2 : 1)} s`
  const minutes = Math.floor(value / 60)
  const rest = Math.round(value % 60)
  return `${minutes}m ${rest}s`
}

export function formatClock(totalSeconds) {
  const safe = Math.max(0, Math.floor(totalSeconds))
  const minutes = String(Math.floor(safe / 60)).padStart(2, '0')
  const seconds = String(safe % 60).padStart(2, '0')
  return `${minutes}:${seconds}`
}

export function formatBytes(bytes) {
  if (bytes === null || bytes === undefined) return '—'
  const value = Number(bytes)
  if (!Number.isFinite(value) || value <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const exponent = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1)
  return `${(value / 1024 ** exponent).toFixed(exponent === 0 ? 0 : 1)} ${units[exponent]}`
}

export function formatPercent(value, digits = 1) {
  if (value === null || value === undefined) return '—'
  return `${(Number(value) * 100).toFixed(digits)}%`
}

export function formatMs(ms) {
  if (ms === null || ms === undefined) return '—'
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(2)} s`
}

export function predictionLabel(prediction) {
  if (prediction === 'synthetic') return 'Potentially synthetic'
  if (prediction === 'genuine') return 'Likely genuine'
  return 'Unable to analyse'
}

export function predictionTone(prediction) {
  if (prediction === 'synthetic') return 'danger'
  if (prediction === 'genuine') return 'success'
  return 'warn'
}

export function statusTone(status) {
  switch (status) {
    case 'completed':
      return 'success'
    case 'failed':
      return 'danger'
    case 'unavailable':
      return 'warn'
    default:
      return 'neutral'
  }
}

export function statusLabel(status) {
  switch (status) {
    case 'completed':
      return 'Completed'
    case 'failed':
      return 'Failed'
    case 'unavailable':
      return 'Model unavailable'
    case 'pending':
      return 'Pending'
    default:
      return status || '—'
  }
}

export const DISCLAIMER =
  'AI voice detection is not 100% reliable. Results should be treated as indicators, not conclusive evidence.'
