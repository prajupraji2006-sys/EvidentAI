// All frontend/backend communication is centralized here. Supabase stays backend-only.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

async function request(path, options) {
  let response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, options)
  } catch {
    throw new Error(`Cannot reach the EvidentAI API at ${API_BASE_URL}. Check that the backend is running.`)
  }

  const raw = await response.text()
  let payload
  try { payload = raw ? JSON.parse(raw) : null } catch { payload = null }
  if (!response.ok) {
    const message = payload?.detail || payload?.message || `API request failed (${response.status})`
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message))
  }
  return payload
}

function uploadWithProgress(file, onProgress) {
  return new Promise((resolve, reject) => {
    const body = new FormData()
    body.append('file', file)
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE_URL}/api/evidence/upload`)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100))
    }
    xhr.onload = () => {
      let payload
      try { payload = xhr.responseText ? JSON.parse(xhr.responseText) : null } catch { payload = null }
      if (xhr.status >= 200 && xhr.status < 300) resolve(payload)
      else reject(new Error(payload?.detail || `Upload failed (${xhr.status})`))
    }
    xhr.onerror = () => reject(new Error('Upload failed because the backend could not be reached.'))
    xhr.onabort = () => reject(new Error('Upload was cancelled.'))
    xhr.send(body)
  })
}

export const api = {
  health: () => request('/api/health'),
  dashboard: () => request('/api/dashboard'),
  cases: () => request('/api/cases'),
  evidence: () => request('/api/evidence'),
  uploadEvidence: uploadWithProgress,
  analyzeEvidence: (evidenceId) => request(`/api/evidence/${encodeURIComponent(evidenceId)}/analyze`, { method: 'POST' }),
  timeline: () => request('/api/timeline'),
  graph: () => request('/api/graph'),
  summary: () => request('/api/summary'),
  integrity: () => request('/api/integrity'),
  verifyEvidence: (evidenceId) => request(`/api/evidence/${encodeURIComponent(evidenceId)}/integrity`),
}
