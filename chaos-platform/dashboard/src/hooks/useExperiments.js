import { useEffect, useCallback } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import {
  fetchExperiments, createExperiment, removeExperiment, fetchExperimentResult,
  selectFilteredExperiments, selectExperimentsLoading, selectExperimentsError,
  setFilters,
} from '../store/slices/experimentsSlice'
import { openModal, closeModal, pushNotification } from '../store/slices/uiSlice'
import { REFRESH_INTERVAL_MS } from '../utils/constants'

export function useExperiments() {
  const dispatch = useDispatch()
  const experiments = useSelector(selectFilteredExperiments)
  const loading = useSelector(selectExperimentsLoading)
  const error = useSelector(selectExperimentsError)

  const refresh = useCallback(() => { dispatch(fetchExperiments()) }, [dispatch])

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, REFRESH_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [refresh])

  const submitExperiment = useCallback(async (payload) => {
    try {
      await dispatch(createExperiment(payload)).unwrap()
      dispatch(closeModal('experimentForm'))
      dispatch(pushNotification({ type: 'success', message: 'Experiment started' }))
    } catch (err) {
      dispatch(pushNotification({ type: 'error', message: err.userMessage ?? err.message ?? 'Failed to create experiment' }))
    }
  }, [dispatch])

  const deleteExp = useCallback(async (id) => {
    try {
      await dispatch(removeExperiment(id)).unwrap()
      dispatch(pushNotification({ type: 'success', message: 'Experiment deleted' }))
    } catch {
      dispatch(pushNotification({ type: 'error', message: 'Failed to delete experiment' }))
    }
  }, [dispatch])

  const loadResult = useCallback((id) => {
    dispatch(fetchExperimentResult(id))
  }, [dispatch])

  const openForm = useCallback(() => dispatch(openModal('experimentForm')), [dispatch])
  const applyFilters = useCallback((f) => dispatch(setFilters(f)), [dispatch])

  return { experiments, loading, error, refresh, submitExperiment, deleteExp, loadResult, openForm, applyFilters }
}
