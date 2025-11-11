import createInstance from './api'

const BASE_URL = import.meta.env.VITE_CHAOS_API_URL || 'http://localhost:8001'

export const chaosApi = createInstance(BASE_URL)

// ── Experiments ──────────────────────────────────────────────────────────────

export const listExperiments = () => chaosApi.get('/experiments')
export const getExperiment = (id) => chaosApi.get(`/experiments/${id}`)
export const createExperiment = (payload) => chaosApi.post('/experiments', payload)
export const deleteExperiment = (id) => chaosApi.delete(`/experiments/${id}`)

// Chaos engine doesn't expose a stop endpoint — reset the circuit breaker instead
export const stopExperiment = () => chaosApi.post('/experiments/circuit-breaker/reset')
export const getCircuitBreaker = () => chaosApi.get('/experiments/circuit-breaker/status')

// ── Results ──────────────────────────────────────────────────────────────────

export const listResults = () => chaosApi.get('/results')
export const getResult = (id) => chaosApi.get(`/results/${id}`)
export const getResultForExperiment = (experimentId) =>
  chaosApi.get(`/results/experiment/${experimentId}`)

// ── Schedules ────────────────────────────────────────────────────────────────

export const listSchedules = () => chaosApi.get('/schedules')
export const createSchedule = (payload) => chaosApi.post('/schedules', payload)
export const updateSchedule = (id, payload) => chaosApi.patch(`/schedules/${id}`, payload)
export const deleteSchedule = (id) => chaosApi.delete(`/schedules/${id}`)
