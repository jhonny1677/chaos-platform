import { createSlice, createAsyncThunk } from '@reduxjs/toolkit'
import * as chaosApi from '../../services/chaosApi'

export const fetchExperiments = createAsyncThunk('experiments/fetchAll', async () => {
  const res = await chaosApi.listExperiments()
  return res.data.experiments ?? []
})

export const createExperiment = createAsyncThunk('experiments/create', async (payload) => {
  const res = await chaosApi.createExperiment(payload)
  return res.data
})

export const removeExperiment = createAsyncThunk('experiments/remove', async (id) => {
  await chaosApi.deleteExperiment(id)
  return id
})

export const fetchExperimentResult = createAsyncThunk('experiments/fetchResult', async (id) => {
  const res = await chaosApi.getResultForExperiment(id)
  return { id, result: res.data }
})

const experimentsSlice = createSlice({
  name: 'experiments',
  initialState: {
    items: [],
    results: {},        // experimentId → result
    loading: false,
    error: null,
    selectedId: null,
    filters: { status: 'all', type: 'all' },
  },
  reducers: {
    setSelectedExperiment: (state, { payload }) => { state.selectedId = payload },
    setFilters: (state, { payload }) => { state.filters = { ...state.filters, ...payload } },
    updateExperiment: (state, { payload }) => {
      const idx = state.items.findIndex((e) => e.experiment_id === payload.experiment_id)
      if (idx >= 0) state.items[idx] = payload
      else state.items.unshift(payload)
    },
    clearError: (state) => { state.error = null },
  },
  extraReducers: (b) => {
    b.addCase(fetchExperiments.pending,   (s) => { s.loading = true; s.error = null })
     .addCase(fetchExperiments.fulfilled, (s, { payload }) => { s.loading = false; s.items = payload })
     .addCase(fetchExperiments.rejected,  (s, { error }) => { s.loading = false; s.error = error.message })
     .addCase(createExperiment.fulfilled, (s, { payload }) => { s.items.unshift(payload) })
     .addCase(removeExperiment.fulfilled, (s, { payload }) => {
       s.items = s.items.filter((e) => e.experiment_id !== payload)
     })
     .addCase(fetchExperimentResult.fulfilled, (s, { payload }) => {
       s.results[payload.id] = payload.result
     })
  },
})

export const { setSelectedExperiment, setFilters, updateExperiment, clearError } = experimentsSlice.actions

// Selectors
export const selectExperiments = (s) => s.experiments.items
export const selectFilteredExperiments = (s) => {
  const { items, filters } = s.experiments
  return items.filter((e) => {
    if (filters.status !== 'all' && e.status !== filters.status) return false
    if (filters.type !== 'all' && e.chaos_type !== filters.type) return false
    return true
  })
}
export const selectSelectedExperiment = (s) =>
  s.experiments.items.find((e) => e.experiment_id === s.experiments.selectedId)
export const selectExperimentsLoading = (s) => s.experiments.loading
export const selectExperimentsError = (s) => s.experiments.error
export const selectExperimentResult = (id) => (s) => s.experiments.results[id]

export default experimentsSlice.reducer
