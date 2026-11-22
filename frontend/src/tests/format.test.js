import { describe, expect, it } from 'vitest'
import {
  formatBytes,
  formatClock,
  formatDuration,
  formatPercent,
  predictionLabel,
  statusLabel,
} from '../utils/format'
import { encodeMonoWav } from '../utils/wav'

describe('format helpers', () => {
  it('formats durations for short and long clips', () => {
    expect(formatDuration(3.456)).toBe('3.46 s')
    expect(formatDuration(75)).toBe('1m 15s')
    expect(formatDuration(null)).toBe('—')
  })

  it('formats clock values used by the recorder', () => {
    expect(formatClock(0)).toBe('00:00')
    expect(formatClock(65)).toBe('01:05')
  })

  it('formats byte sizes', () => {
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(2048)).toBe('2.0 KB')
    expect(formatBytes(null)).toBe('—')
  })

  it('formats probabilities', () => {
    expect(formatPercent(0.1234)).toBe('12.3%')
    expect(formatPercent(null)).toBe('—')
  })

  it('maps predictions and statuses to readable labels', () => {
    expect(predictionLabel('synthetic')).toBe('Potentially synthetic')
    expect(predictionLabel('genuine')).toBe('Likely genuine')
    expect(statusLabel('unavailable')).toBe('Model unavailable')
  })
})

// jsdom's Blob does not implement arrayBuffer(); FileReader does.
function readBlob(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = () => reject(reader.error)
    reader.readAsArrayBuffer(blob)
  })
}

describe('WAV encoder', () => {
  it('writes a valid mono PCM WAV header', async () => {
    const samples = new Float32Array([0, 0.5, -0.5, 1, -1])
    const blob = encodeMonoWav(samples, 16000)
    expect(blob.type).toBe('audio/wav')

    const arrayBuffer = await readBlob(blob)
    const buffer = new Uint8Array(arrayBuffer)
    const header = new TextDecoder().decode(buffer.slice(0, 4))
    expect(header).toBe('RIFF')
    expect(new TextDecoder().decode(buffer.slice(8, 12))).toBe('WAVE')

    const view = new DataView(buffer.buffer)
    expect(view.getUint16(22, true)).toBe(1) // mono
    expect(view.getUint32(24, true)).toBe(16000) // sample rate
    expect(view.getUint16(34, true)).toBe(16) // bits per sample
    expect(buffer.length).toBe(44 + samples.length * 2)
  })
})
