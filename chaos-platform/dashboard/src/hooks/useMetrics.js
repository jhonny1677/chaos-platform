import { useEffect, useCallback } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { fetchPods, fetchAlerts, setRequestRateData, setErrorRateData } from '../store/slices/metricsSlice'
import { selectPods, selectAlerts } from '../store/slices/metricsSlice'
import * as metricsApi from '../services/metricsApi'
import { REFRESH_INTERVAL_MS } from '../utils/constants'

function parseRangeResult(result, key = 'value') {
  return (result ?? []).map(([ts, val]) => ({
    time: new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
    [key]: parseFloat(val) || 0,
  }))
}

export function useMetrics(namespace = 'target-app') {
  const dispatch = useDispatch()
  const pods   = useSelector(selectPods)
  const alerts = useSelector(selectAlerts)

  const fetchRateData = useCallback(async () => {
    try {
      const [rps, err] = await Promise.all([
        metricsApi.fetchRequestRate(namespace, 5),
        metricsApi.fetchErrorRate(namespace, 5),
      ])
      const rpsValues = rps.data?.data?.result?.[0]?.values ?? []
      const errValues = err.data?.data?.result?.[0]?.values ?? []
      dispatch(setRequestRateData(parseRangeResult(rpsValues, 'rps')))
      dispatch(setErrorRateData(parseRangeResult(errValues, 'error_rate')))
    } catch { /* Prometheus unavailable — leave data as-is */ }
  }, [dispatch, namespace])

  const refresh = useCallback(() => {
    dispatch(fetchPods(namespace))
    dispatch(fetchAlerts())
    fetchRateData()
  }, [dispatch, namespace, fetchRateData])

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, REFRESH_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [refresh])

  return { pods, alerts, refresh }
}
