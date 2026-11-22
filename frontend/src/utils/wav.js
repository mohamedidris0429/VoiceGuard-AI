/**
 * Convert a MediaRecorder blob (audio/webm or audio/ogg) into a mono 16-bit
 * PCM WAV file. The backend deliberately accepts only WAV/MP3, so encoding in
 * the browser keeps recordings on exactly the same analysis pipeline.
 */
export async function recordingToWavBlob(blob) {
  const arrayBuffer = await blob.arrayBuffer()
  const AudioContextClass = window.AudioContext || window.webkitAudioContext
  if (!AudioContextClass) {
    throw new Error('This browser cannot decode the recording.')
  }

  const context = new AudioContextClass()
  let audioBuffer
  try {
    audioBuffer = await context.decodeAudioData(arrayBuffer.slice(0))
  } finally {
    context.close().catch(() => {})
  }

  const channelCount = Math.min(2, audioBuffer.numberOfChannels)
  const length = audioBuffer.length
  const mono = new Float32Array(length)
  for (let channel = 0; channel < channelCount; channel += 1) {
    const data = audioBuffer.getChannelData(channel)
    for (let index = 0; index < length; index += 1) {
      mono[index] += data[index] / channelCount
    }
  }

  return encodeMonoWav(mono, audioBuffer.sampleRate)
}

export function encodeMonoWav(samples, sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2)
  const view = new DataView(buffer)

  const writeString = (offset, text) => {
    for (let index = 0; index < text.length; index += 1) {
      view.setUint8(offset + index, text.charCodeAt(index))
    }
  }

  writeString(0, 'RIFF')
  view.setUint32(4, 36 + samples.length * 2, true)
  writeString(8, 'WAVE')
  writeString(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // mono
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true) // byte rate
  view.setUint16(32, 2, true) // block align
  view.setUint16(34, 16, true) // bits per sample
  writeString(36, 'data')
  view.setUint32(40, samples.length * 2, true)

  let offset = 44
  for (let index = 0; index < samples.length; index += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[index]))
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true)
    offset += 2
  }

  return new Blob([buffer], { type: 'audio/wav' })
}

export function wavFileName(prefix = 'voiceguard-recording') {
  const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
  return `${prefix}-${stamp}.wav`
}
