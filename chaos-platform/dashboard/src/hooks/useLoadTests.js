import { useEffect, useCallback } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import {
  fetchTests, createTest, removeTest,
  selectTests, selectTestsLoading, selectActiveTests,
} from '../store/slices/loadTestsSlice'
import { openModal, closeModal, pushNotification } from '../store/slices/uiSlice'
import { REFRESH_INTERVAL_MS } from '../utils/constants'
import * as loadTestApi from '../services/loadTestApi'

export function useLoadTests() {
  const dispatch = useDispatch()
  const tests = useSelector(selectTests)
  const loading = useSelector(selectTestsLoading)
  const activeTests = useSelector(selectActiveTests)

  const refresh = useCallback(() => { dispatch(fetchTests()) }, [dispatch])

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, REFRESH_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [refresh])

  const submitTest = useCallback(async (payload) => {
    try {
      await dispatch(createTest(payload)).unwrap()
      dispatch(closeModal('testForm'))
      dispatch(pushNotification({ type: 'success', message: 'Load test started' }))
    } catch (err) {
      dispatch(pushNotification({ type: 'error', message: err.userMessage ?? 'Failed to start test' }))
    }
  }, [dispatch])

  const deleteTestById = useCallback(async (id) => {
    try {
      await dispatch(removeTest(id)).unwrap()
      dispatch(pushNotification({ type: 'success', message: 'Test deleted' }))
    } catch {
      dispatch(pushNotification({ type: 'error', message: 'Failed to delete test' }))
    }
  }, [dispatch])

  const stopTestById = useCallback(async (id) => {
    try {
      await loadTestApi.stopTest(id)
      refresh()
      dispatch(pushNotification({ type: 'success', message: 'Test stopped' }))
    } catch {
      dispatch(pushNotification({ type: 'error', message: 'Failed to stop test' }))
    }
  }, [dispatch, refresh])

  const openForm = useCallback(() => dispatch(openModal('testForm')), [dispatch])

  return { tests, loading, activeTests, refresh, submitTest, deleteTestById, stopTestById, openForm }
}
