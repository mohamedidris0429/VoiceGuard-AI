const DEFAULT_BASE = 'http://127.0.0.1:8000/api'

export const API_BASE = (import.meta.env.VITE_API_BASE_URL || DEFAULT_BASE).replace(/\/+$/, '')

const TOKEN_KEY = 'voiceguard.token'

export class ApiError extends Error {
  constructor(message, status = 0, code = 'request_failed') {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* private mode - session stays in memory only */
  }
}

function authHeaders(extra = {}) {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}`, ...extra } : { ...extra }
}

function handleUnauthorized() {
  setToken(null)
  window.dispatchEvent(new Event('voiceguard:unauthorized'))
}

async function parseError(response) {
  let detail = `Request failed with status ${response.status}.`
  let code = 'http_error'
  try {
    const payload = await response.json()
    if (payload && typeof payload.detail === 'string') detail = payload.detail
    if (payload && payload.code) code = payload.code
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(detail, response.status, code)
}

async function request(path, { method = 'GET', json, body, auth = true, signal, raw = false } = {}) {
  const headers = auth ? authHeaders() : {}
  let payload = body
  if (json !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(json)
  }

  let response
  try {
    response = await fetch(`${API_BASE}${path}`, { method, headers, body: payload, signal })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new ApiError(
      'Cannot reach the VoiceGuard AI API. Check that the backend is running.',
      0,
      'network_error',
    )
  }

  if (response.status === 401 && auth) {
    handleUnauthorized()
  }
  if (!response.ok) throw await parseError(response)
  if (raw) return response
  if (response.status === 204) return null
  return response.json()
}

function uploadWithProgress(path, formData, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE}${path}`)
    const token = getToken()
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)

    if (xhr.upload && onProgress) {
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          onProgress(Math.min(99, Math.round((event.loaded / event.total) * 100)))
        }
      }
    }
    xhr.onload = () => {
      let data = null
      try {
        data = JSON.parse(xhr.responseText || '{}')
      } catch {
        /* ignore */
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        if (onProgress) onProgress(100)
        resolve(data)
      } else {
        if (xhr.status === 401) handleUnauthorized()
        reject(
          new ApiError(
            (data && data.detail) || `Upload failed with status ${xhr.status}.`,
            xhr.status,
            (data && data.code) || 'upload_failed',
          ),
        )
      }
    }
    xhr.onerror = () => reject(new ApiError('Network error while uploading the file.', 0, 'network_error'))
    xhr.send(formData)
  })
}

function filenameFromDisposition(header, fallback) {
  if (!header) return fallback
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(header)
  if (utf8) return decodeURIComponent(utf8[1])
  const basic = /filename="?([^";]+)"?/i.exec(header)
  return basic ? basic[1] : fallback
}

export const authApi = {
  login: (email, password) =>
    request('/auth/login', { method: 'POST', json: { email, password }, auth: false }),
  register: (payload) =>
    request('/auth/register', { method: 'POST', json: payload, auth: false }),
  me: () => request('/auth/me'),
  updateProfile: (payload) => request('/auth/me', { method: 'PATCH', json: payload }),
  changePassword: (payload) =>
    request('/auth/change-password', { method: 'POST', json: payload }),
}

export const audioApi = {
  upload: (file, onProgress) => {
    const formData = new FormData()
    formData.append('file', file)
    return uploadWithProgress('/audio/upload', formData, onProgress)
  },
  analyze: (analysisId) =>
    request('/audio/analyze', { method: 'POST', json: { analysis_id: analysisId } }),
  get: (analysisId) => request(`/audio/${analysisId}`),
  remove: (analysisId) => request(`/audio/${analysisId}`, { method: 'DELETE' }),
  waveform: (analysisId, buckets = 800) =>
    request(`/audio/${analysisId}/waveform?buckets=${buckets}`),
  spectrogramBlob: async (analysisId) => {
    const response = await request(`/audio/${analysisId}/spectrogram`, { raw: true })
    return response.blob()
  },
  compare: (fileA, fileB, onProgress) => {
    const formData = new FormData()
    formData.append('file_a', fileA)
    formData.append('file_b', fileB)
    return uploadWithProgress('/audio/compare', formData, onProgress)
  },
  limits: () => request('/audio/limits/info', { auth: false }),
}

export const forensicsApi = {
  get: (analysisId) => request(`/forensics/${analysisId}`),
  mediaBlob: async (analysisId) => {
    const response = await request(`/forensics/${analysisId}/media`, { raw: true })
    return response.blob()
  },
  segmentSignal: (analysisId) => request(`/forensics/${analysisId}/segment-signal`),
}

export const segmentsApi = {
  get: (analysisId) => request(`/forensics/${analysisId}/segments`),
  compute: (analysisId, params = {}) => {
    const query = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') query.set(key, value)
    })
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return request(`/forensics/${analysisId}/segments${suffix}`, { method: 'POST' })
  },
}

export const streamApi = {
  create: (chunkSeconds = 3) =>
    request('/stream/sessions', { method: 'POST', json: { chunk_seconds: chunkSeconds } }),
  get: (sessionId) => request(`/stream/sessions/${sessionId}`),
  stop: (sessionId) => request(`/stream/sessions/${sessionId}/stop`, { method: 'POST' }),
  discard: (sessionId) => request(`/stream/sessions/${sessionId}`, { method: 'DELETE' }),
  sendChunk: async (sessionId, blob, index, filename = `chunk-${index}.wav`) => {
    const formData = new FormData()
    formData.append('file', blob, filename)
    formData.append('chunk_index', String(index))
    const response = await request(`/stream/sessions/${sessionId}/chunks`, {
      method: 'POST',
      body: formData,
    })
    return response
  },
}

export const historyApi = {
  list: (params = {}) => {
    const query = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') query.set(key, value)
    })
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return request(`/history${suffix}`)
  },
  get: (analysisId) => request(`/history/${analysisId}`),
}

export const analyticsApi = {
  summary: () => request('/analytics/summary'),
  trends: (days = 14) => request(`/analytics/trends?days=${days}`),
}

export const reportsApi = {
  download: async (analysisId) => {
    const response = await request(`/reports/${analysisId}/download`, { raw: true })
    const blob = await response.blob()
    const filename = filenameFromDisposition(
      response.headers.get('content-disposition'),
      `voiceguard-report-${analysisId}.pdf`,
    )
    return { blob, filename }
  },
  metadata: (analysisId) => request(`/reports/${analysisId}/metadata`),
}

export const systemApi = {
  health: () => request('/health'),
  modelStatus: (load = false) => request(`/model/status${load ? '?load=true' : ''}`, { auth: false }),
}

export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  setTimeout(() => URL.revokeObjectURL(url), 4000)
}
