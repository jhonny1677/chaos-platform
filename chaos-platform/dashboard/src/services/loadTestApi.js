import createInstance from './api'

const BASE_URL = import.meta.env.VITE_LOADTEST_API_URL || 'http://localhost:8002'

export const loadTestApi = createInstance(BASE_URL)

// ── Tests ────────────────────────────────────────────────────────────────────

export const listTests = () => loadTestApi.get('/tests')
export const getTest = (id) => loadTestApi.get(`/tests/${id}`)
export const createTest = (payload) => loadTestApi.post('/tests', payload)
export const deleteTest = (id) => loadTestApi.delete(`/tests/${id}`)
export const stopTest = (id) => loadTestApi.post(`/tests/${id}/stop`)
export const abortTest = (id) => loadTestApi.post(`/tests/${id}/abort`)
export const getTestStatus = (id) => loadTestApi.get(`/tests/${id}/status`)

// ── Results ──────────────────────────────────────────────────────────────────

export const getLiveStats = (testId) => loadTestApi.get(`/results/live/${testId}`)
export const getTestSnapshots = (testId) => loadTestApi.get(`/results/${testId}`)

// ── Workers ──────────────────────────────────────────────────────────────────

export const listWorkers = () => loadTestApi.get('/workers')
export const getTestWorkers = (testId) => loadTestApi.get(`/workers/${testId}`)
