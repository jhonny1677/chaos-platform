import { useState } from 'react'
import { useDispatch } from 'react-redux'
import { pushNotification } from '../store/slices/uiSlice'
import { chaosApi } from '../services/chaosApi'

export default function Settings() {
  const dispatch = useDispatch()
  const [cbStatus, setCbStatus] = useState(null)
  const [cbLoading, setCbLoading] = useState(false)

  const fetchCbStatus = async () => {
    setCbLoading(true)
    try {
      const res = await chaosApi.get('/experiments/circuit-breaker/status')
      setCbStatus(res.data)
    } catch {
      dispatch(pushNotification({ type: 'error', message: 'Could not reach chaos engine' }))
    } finally {
      setCbLoading(false)
    }
  }

  const resetCircuitBreaker = async () => {
    try {
      await chaosApi.post('/experiments/circuit-breaker/reset')
      dispatch(pushNotification({ type: 'success', message: 'Circuit breaker reset — experiments re-enabled' }))
      await fetchCbStatus()
    } catch {
      dispatch(pushNotification({ type: 'error', message: 'Reset failed' }))
    }
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="card space-y-4">
        <h2 className="section-title">Chaos Engine</h2>

        <div className="flex items-center justify-between py-2 border-b border-gray-700">
          <div>
            <p className="text-sm font-medium text-gray-200">Circuit Breaker</p>
            <p className="text-xs text-gray-500 mt-0.5">
              Opens after 3 consecutive hypothesis failures. Must be manually reset.
            </p>
          </div>
          <button onClick={fetchCbStatus} className="btn-ghost text-sm" disabled={cbLoading}>
            {cbLoading ? 'Checking…' : 'Check status'}
          </button>
        </div>

        {cbStatus !== null && (
          <div className={`flex items-center justify-between px-4 py-3 rounded-lg border ${
            cbStatus.is_open
              ? 'bg-red-900/30 border-red-800'
              : 'bg-green-900/20 border-green-800'
          }`}>
            <div>
              <p className={`text-sm font-semibold ${cbStatus.is_open ? 'text-red-300' : 'text-green-300'}`}>
                {cbStatus.is_open ? '⚡ Circuit breaker OPEN — experiments blocked' : '✓ Circuit breaker closed — experiments allowed'}
              </p>
              {cbStatus.consecutive_failures != null && (
                <p className="text-xs text-gray-400 mt-0.5">
                  Consecutive failures: {cbStatus.consecutive_failures} / 3
                </p>
              )}
            </div>
            {cbStatus.is_open && (
              <button onClick={resetCircuitBreaker} className="btn-danger text-sm ml-4">Reset</button>
            )}
          </div>
        )}
      </div>

      <div className="card space-y-3">
        <h2 className="section-title">API Endpoints</h2>
        {[
          { label: 'Chaos Engine',   key: 'VITE_CHAOS_API_URL',    fallback: 'http://localhost:8001' },
          { label: 'Load Tester',    key: 'VITE_LOADTEST_API_URL', fallback: 'http://localhost:8002' },
          { label: 'Prometheus',     key: 'VITE_PROMETHEUS_URL',   fallback: 'http://localhost:9090' },
          { label: 'Alertmanager',   key: 'VITE_ALERTMANAGER_URL', fallback: 'http://localhost:9093' },
          { label: 'WebSocket',      key: 'VITE_WS_URL',           fallback: 'ws://localhost:8001' },
        ].map(({ label, key, fallback }) => (
          <div key={key} className="flex items-center justify-between py-2 border-b border-gray-700 last:border-0">
            <span className="text-sm text-gray-400">{label}</span>
            <span className="text-xs font-mono text-gray-300 bg-gray-700 px-2 py-1 rounded">
              {import.meta.env[key] || fallback}
            </span>
          </div>
        ))}
        <p className="text-xs text-gray-600 pt-1">
          Override via env vars in k8s/configmap.yaml and rebuild.
        </p>
      </div>

      <div className="card space-y-2">
        <h2 className="section-title">Platform</h2>
        <div className="grid grid-cols-2 gap-2 text-sm">
          {[
            ['Chaos Engine',  'Phase 4 — FastAPI + Kubernetes client'],
            ['Load Tester',   'Phase 5 — asyncio + httpx + KEDA'],
            ['Dashboard',     'Phase 6 — React 18 + Redux Toolkit'],
            ['Infrastructure', 'Phase 1 — Terraform + EKS v1.29 SPOT'],
          ].map(([k, v]) => (
            <div key={k} className="bg-gray-700 rounded-lg p-3">
              <p className="text-xs text-gray-500">{k}</p>
              <p className="text-xs text-gray-300 mt-0.5">{v}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
