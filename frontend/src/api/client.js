import axios from 'axios'

const api = axios.create({
  baseURL: '/v1',
  headers: { 'Content-Type': 'application/json' },
})

// ── Incidents ──────────────────────────────────────────
export const incidentApi = {
  list: (params) => api.get('/incidents', { params }).then(r => r.data),
  get: (id) => api.get(`/incidents/${id}`).then(r => r.data),
  create: (data) => api.post('/incidents', data).then(r => r.data),
  update: (id, data) => api.put(`/incidents/${id}`, data).then(r => r.data),
  delete: (id) => api.delete(`/incidents/${id}`),
  search: (params) => api.get('/incidents/search', { params }).then(r => r.data),
}

// ── Triage ─────────────────────────────────────────────
export const triageApi = {
  run: (id) => api.post(`/triage/${id}`).then(r => r.data),
  context: (id) => api.get(`/triage/${id}/context`).then(r => r.data),
}

// ── Shift Roster ───────────────────────────────────────
export const rosterApi = {
  upload: (file, uploadedBy) => {
    const form = new FormData()
    form.append('file', file)
    const params = uploadedBy ? `?uploaded_by=${encodeURIComponent(uploadedBy)}` : ''
    return api.post(`/shift-roster/upload${params}`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
  },
  uploadBulk: (files, uploadedBy) => {
    const form = new FormData()
    files.forEach(f => form.append('files', f))
    const params = uploadedBy ? `?uploaded_by=${encodeURIComponent(uploadedBy)}` : ''
    return api.post(`/shift-roster/upload-bulk${params}`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
  },
  uploads: () => api.get('/shift-roster/uploads').then(r => r.data),
  available: (params) => api.get('/shift-roster/available', { params }).then(r => r.data),
  searchEngineers: (params) => api.get('/shift-roster/search', { params }).then(r => r.data),
}

export default api
