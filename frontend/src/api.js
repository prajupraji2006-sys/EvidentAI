// All frontend/backend communication is centralized here. Supabase stays backend-only.
import { clearExpiredSession, getAccessToken } from './auth.jsx'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') || ''

async function request(path, options) {
  let response
  const token = await getAccessToken()
  if (!API_BASE_URL) throw new Error('Set VITE_API_BASE_URL before using the EvidentAI API.')
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: { ...(options?.headers || {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    })
  } catch {
    throw new Error(`Cannot reach the EvidentAI API at ${API_BASE_URL}. Check that the backend is running.`)
  }

  const raw = await response.text()
  let payload
  try { payload = raw ? JSON.parse(raw) : null } catch { payload = null }
  if (!response.ok) {
    if (response.status === 401) await clearExpiredSession()
    const message = payload?.detail || payload?.message || `API request failed (${response.status})`
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message))
  }
  return payload
}

async function uploadWithProgress(file, incidentId, onProgress) {
  const token = await getAccessToken()
  if (!token) throw new Error('Your session expired. Sign in again before uploading.')
  if (!API_BASE_URL) throw new Error('Set VITE_API_BASE_URL before uploading evidence.')
  return new Promise((resolve, reject) => {
    const body = new FormData()
    body.append('file', file)
    body.append('incident_id', incidentId)
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE_URL}/api/evidence/upload`)
    xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100))
    }
    xhr.onload = () => {
      let payload
      try { payload = xhr.responseText ? JSON.parse(xhr.responseText) : null } catch { payload = null }
      if (xhr.status >= 200 && xhr.status < 300) resolve(payload)
      else {
        if (xhr.status === 401) clearExpiredSession()
        reject(new Error(payload?.detail || `Upload failed (${xhr.status})`))
      }
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
  createCase: (body) => request('/api/cases', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  evidence: () => request('/api/evidence'),
  uploadEvidence: uploadWithProgress,
  analyzeEvidence: (evidenceId) => request(`/api/evidence/${encodeURIComponent(evidenceId)}/analyze`, { method: 'POST' }),
  timeline: () => request('/api/timeline'),
  graph: () => request('/api/graph'),
  summary: () => request('/api/summary'),
  integrity: () => request('/api/integrity'),
  verifyEvidence: (evidenceId) => request(`/api/evidence/${encodeURIComponent(evidenceId)}/integrity`),
  assessAuthenticity: (evidenceId) => request(`/api/evidence/${encodeURIComponent(evidenceId)}/authenticity-assessment`, { method: 'POST' }),
  authenticityAssessment: (evidenceId) => request(`/api/evidence/${encodeURIComponent(evidenceId)}/authenticity-assessment`),
  audit: (limit = 100) => request(`/api/audit?limit=${limit}`),
  recordLogin: () => request('/api/audit/login', { method: 'POST' }),
  bootstrapProfile: () => request('/api/profile/bootstrap', { method: 'POST' }),
}
