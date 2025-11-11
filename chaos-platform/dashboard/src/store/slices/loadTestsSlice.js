import { createSlice, createAsyncThunk } from '@reduxjs/toolkit'
import * as loadTestApi from '../../services/loadTestApi'

export const fetchTests = createAsyncThunk('loadTests/fetchAll', async () => {
  const res = await loadTestApi.listTests()
  return res.data.tests ?? []
})

export const createTest = createAsyncThunk('loadTests/create', async (payload) => {
  const res = await loadTestApi.createTest(payload)
  return res.data
})

export const removeTest = createAsyncThunk('loadTests/remove', async (id) => {
  await loadTestApi.deleteTest(id)
  return id
})

export const fetchLiveStats = createAsyncThunk('loadTests/fetchLiveStats', async (testId) => {
  const res = await loadTestApi.getLiveStats(testId)
  return res.data
})

export const fetchSnapshots = createAsyncThunk('loadTests/fetchSnapshots', async (testId) => {
  const res = await loadTestApi.getTestSnapshots(testId)
  return { testId, snapshots: res.data.snapshots ?? [] }
})

const loadTestsSlice = createSlice({
  name: 'loadTests',
  initialState: {
    items: [],
    snapshots: {},      // testId → snapshot[]
    liveStats: null,
    loading: false,
    error: null,
    selectedId: null,
  },
  reducers: {
    setSelectedTest: (state, { payload }) => { state.selectedId = payload },
    setLiveStats: (state, { payload }) => { state.liveStats = payload },
    updateTest: (state, { payload }) => {
      const idx = state.items.findIndex((t) => t.test_id === payload.test_id)
      if (idx >= 0) state.items[idx] = payload
      else state.items.unshift(payload)
    },
    clearError: (state) => { state.error = null },
  },
  extraReducers: (b) => {
    b.addCase(fetchTests.pending,    (s) => { s.loading = true; s.error = null })
     .addCase(fetchTests.fulfilled,  (s, { payload }) => { s.loading = false; s.items = payload })
     .addCase(fetchTests.rejected,   (s, { error }) => { s.loading = false; s.error = error.message })
     .addCase(createTest.fulfilled,  (s, { payload }) => { s.items.unshift(payload) })
     .addCase(removeTest.fulfilled,  (s, { payload }) => {
       s.items = s.items.filter((t) => t.test_id !== payload)
     })
     .addCase(fetchLiveStats.fulfilled, (s, { payload }) => { s.liveStats = payload })
     .addCase(fetchSnapshots.fulfilled, (s, { payload }) => {
       s.snapshots[payload.testId] = payload.snapshots
     })
  },
})

export const { setSelectedTest, setLiveStats, updateTest, clearError } = loadTestsSlice.actions

export const selectTests = (s) => s.loadTests.items
export const selectTestsLoading = (s) => s.loadTests.loading
export const selectSelectedTest = (s) =>
  s.loadTests.items.find((t) => t.test_id === s.loadTests.selectedId)
export const selectLiveStats = (s) => s.loadTests.liveStats
export const selectSnapshots = (id) => (s) => s.loadTests.snapshots[id] ?? []
export const selectActiveTests = (s) => s.loadTests.items.filter((t) => t.status === 'running')

export default loadTestsSlice.reducer
