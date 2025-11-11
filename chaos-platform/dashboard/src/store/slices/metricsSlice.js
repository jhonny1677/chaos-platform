import { createSlice, createAsyncThunk } from '@reduxjs/toolkit'
import * as metricsApi from '../../services/metricsApi'

export const fetchPods = createAsyncThunk('metrics/fetchPods', async (namespace = 'target-app') => {
  try {
    const [info, ready, restarts] = await Promise.all([
      metricsApi.fetchPodStatus(namespace),
      metricsApi.fetchPodReadiness(namespace),
      metricsApi.fetchPodRestarts(namespace),
    ])
    const pods = (info.data?.data?.result ?? []).map((r) => {
      const pod = r.metric.pod
      const isReady = (ready.data?.data?.result ?? []).some(
        (x) => x.metric.pod === pod && x.value[1] === '1'
      )
      const restartEntry = (restarts.data?.data?.result ?? []).find((x) => x.metric.pod === pod)
      return {
        name: pod,
        namespace,
        ready: isReady,
        phase: isReady ? 'Running' : 'Pending',
        restarts: restartEntry ? parseInt(restartEntry.value[1], 10) : 0,
        cpu: 0,
        memoryMb: 0,
      }
    })
    return pods
  } catch {
    return []
  }
})

export const fetchAlerts = createAsyncThunk('metrics/fetchAlerts', async () => {
  try {
    const res = await metricsApi.fetchAlerts()
    return res.data ?? []
  } catch { return [] }
})

const metricsSlice = createSlice({
  name: 'metrics',
  initialState: {
    pods: [],
    alerts: [],
    requestRateData: [],
    errorRateData: [],
    loading: false,
    killedPods: [],   // recently chaos-killed pods (fed by WebSocket)
  },
  reducers: {
    setRequestRateData: (state, { payload }) => { state.requestRateData = payload },
    setErrorRateData:   (state, { payload }) => { state.errorRateData   = payload },
    markPodKilled: (state, { payload }) => {
      state.killedPods = [payload, ...state.killedPods].slice(0, 50)
    },
  },
  extraReducers: (b) => {
    b.addCase(fetchPods.pending,    (s) => { s.loading = true })
     .addCase(fetchPods.fulfilled,  (s, { payload }) => { s.loading = false; s.pods = payload })
     .addCase(fetchPods.rejected,   (s) => { s.loading = false })
     .addCase(fetchAlerts.fulfilled, (s, { payload }) => { s.alerts = payload })
  },
})

export const { setRequestRateData, setErrorRateData, markPodKilled } = metricsSlice.actions

export const selectPods       = (s) => s.metrics.pods
export const selectAlerts     = (s) => s.metrics.alerts
export const selectKilledPods = (s) => s.metrics.killedPods
export const selectRateData   = (s) => ({ request: s.metrics.requestRateData, error: s.metrics.errorRateData })

export default metricsSlice.reducer
