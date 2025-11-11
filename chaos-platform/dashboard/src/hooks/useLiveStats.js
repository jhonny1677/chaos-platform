import { useEffect, useRef, useCallback } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { setLiveStats, selectLiveStats } from '../store/slices/loadTestsSlice'
import { getLiveStats } from '../services/loadTestApi'
import { LIVE_STATS_INTERVAL_MS } from '../utils/constants'

// Polls REST endpoint every second as fallback to WebSocket updates
export function useLiveStats(testId) {
  const dispatch = useDispatch()
  const liveStats = useSelector(selectLiveStats)
  const timer = useRef(null)
  const active = useRef(false)

  const poll = useCallback(async () => {
    if (!testId || !active.current) return
    try {
      const res = await getLiveStats(testId)
      dispatch(setLiveStats(res.data))
    } catch { /* test may have ended */ }
  }, [testId, dispatch])

  useEffect(() => {
    if (!testId) { dispatch(setLiveStats(null)); return }
    active.current = true
    poll()
    timer.current = setInterval(poll, LIVE_STATS_INTERVAL_MS)
    return () => {
      active.current = false
      clearInterval(timer.current)
    }
  }, [testId, poll, dispatch])

  return liveStats
}
