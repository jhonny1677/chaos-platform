import { configureStore } from '@reduxjs/toolkit'
import experimentsReducer from './slices/experimentsSlice'
import loadTestsReducer from './slices/loadTestsSlice'
import metricsReducer from './slices/metricsSlice'
import uiReducer from './slices/uiSlice'

const store = configureStore({
  reducer: {
    experiments: experimentsReducer,
    loadTests:   loadTestsReducer,
    metrics:     metricsReducer,
    ui:          uiReducer,
  },
})

export default store
