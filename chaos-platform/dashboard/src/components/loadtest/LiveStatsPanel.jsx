import { Activity, Users, AlertTriangle, Clock } from 'lucide-react'
import { fmtRps, fmtPct, fmtMs, fmtCount } from '../../utils/formatters'
import LatencyChart from '../charts/LatencyChart'
import RequestRateChart from '../charts/RequestRateChart'
import ErrorRateChart from '../charts/ErrorRateChart'
import { useSelector } from 'react-redux'
import { selectLiveStats } from '../../store/slices/loadTestsSlice'

function StatTile({ icon: Icon, label, value, color = 'text-blue-400' }) {
  return (
    <div className="card flex items-center gap-3">
      <div className={`p-2 rounded-lg bg-gray-700 ${color}`}>
        <Icon size={18} />
      </div>
      <div>
        <p className="text-xs text-gray-500">{label}</p>
        <p className={`text-lg font-bold ${color}`}>{value}</p>
      </div>
    </div>
  )
}

export default function LiveStatsPanel({ historyData = [] }) {
  const stats = useSelector(selectLiveStats)

  if (!stats) {
    return (
      <div className="card text-center py-8 text-gray-500">
        <Activity size={24} className="mx-auto mb-2 animate-pulse" />
        <p className="text-sm">Waiting for live data…</p>
        <p className="text-xs mt-1">Stats update every second once the test is running.</p>
      </div>
    )
  }

  const errorPct = stats.total_requests > 0
    ? (stats.failed_requests / stats.total_requests) * 100
    : 0

  return (
    <div className="space-y-4">
      {/* KPI tiles */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile icon={Activity} label="Req / s" value={fmtRps(stats.requests_per_second)} color="text-blue-400" />
        <StatTile icon={Users}    label="Active VU" value={stats.active_workers ?? '—'} color="text-purple-400" />
        <StatTile icon={AlertTriangle} label="Error rate"
          value={fmtPct(errorPct)}
          color={errorPct > 5 ? 'text-red-400' : 'text-green-400'} />
        <StatTile icon={Clock}    label="p99 latency" value={fmtMs(stats.p99_ms)} color="text-yellow-400" />
      </div>

      {/* Secondary stats */}
      <div className="card grid grid-cols-3 gap-4 text-center">
        <div>
          <p className="text-xs text-gray-500 mb-1">Total requests</p>
          <p className="text-base font-semibold text-gray-100">{fmtCount(stats.total_requests)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500 mb-1">p50 latency</p>
          <p className="text-base font-semibold text-gray-100">{fmtMs(stats.p50_ms)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500 mb-1">p95 latency</p>
          <p className="text-base font-semibold text-gray-100">{fmtMs(stats.p95_ms)}</p>
        </div>
      </div>

      {/* Live charts */}
      {historyData.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="card">
            <p className="section-title text-sm mb-3">Request Rate</p>
            <RequestRateChart data={historyData} height={180} />
          </div>
          <div className="card">
            <p className="section-title text-sm mb-3">Latency (p50/p95/p99)</p>
            <LatencyChart data={historyData} height={180} />
          </div>
        </div>
      )}
    </div>
  )
}
