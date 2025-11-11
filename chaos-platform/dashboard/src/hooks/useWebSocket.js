import { useEffect, useRef, useState, useCallback } from 'react'
import { useDispatch } from 'react-redux'
import { setWsStatus } from '../store/slices/uiSlice'
import { updateExperiment } from '../store/slices/experimentsSlice'
import { updateTest, setLiveStats } from '../store/slices/loadTestsSlice'
import { markPodKilled } from '../store/slices/metricsSlice'

const WS_BASE = import.meta.env.VITE_WS_URL || 'ws://localhost:8001'
const MAX_BACKOFF_MS = 30_000

export function useWebSocket() {
  const dispatch = useDispatch()
  const ws = useRef(null)
  const retryTimer = useRef(null)
  const attempts = useRef(0)
  const stopping = useRef(false)
  const [connStatus, setConnStatus] = useState('disconnected')

  const handleMessage = useCallback((msg) => {
    switch (msg.type) {
      case 'experiment_update':
        dispatch(updateExperiment(msg.data))
        break
      case 'pod_killed':
        dispatch(markPodKilled(msg.data))
        break
      case 'live_stats':
        dispatch(setLiveStats(msg.data))
        break
      case 'test_update':
        dispatch(updateTest(msg.data))
        break
      default:
        break
    }
  }, [dispatch])

  const connect = useCallback(() => {
    if (stopping.current) return
    try {
      const sock = new WebSocket(`${WS_BASE}/ws`)
      ws.current = sock

      sock.onopen = () => {
        attempts.current = 0
        setConnStatus('connected')
        dispatch(setWsStatus('connected'))
      }

      sock.onmessage = (event) => {
        try { handleMessage(JSON.parse(event.data)) } catch { /* non-JSON, ignore */ }
      }

      sock.onclose = () => {
        if (stopping.current) return
        setConnStatus('reconnecting')
        dispatch(setWsStatus('reconnecting'))
        const delay = Math.min(1_000 * 2 ** attempts.current, MAX_BACKOFF_MS)
        attempts.current++
        retryTimer.current = setTimeout(connect, delay)
      }

      sock.onerror = () => {
        sock.close()
      }
    } catch {
      const delay = Math.min(1_000 * 2 ** attempts.current, MAX_BACKOFF_MS)
      attempts.current++
      retryTimer.current = setTimeout(connect, delay)
    }
  }, [handleMessage, dispatch])

  useEffect(() => {
    connect()
    return () => {
      stopping.current = true
      clearTimeout(retryTimer.current)
      ws.current?.close()
      dispatch(setWsStatus('disconnected'))
    }
  }, [connect, dispatch])

  const send = useCallback((data) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(data))
    }
  }, [])

  return { status: connStatus, send }
}
