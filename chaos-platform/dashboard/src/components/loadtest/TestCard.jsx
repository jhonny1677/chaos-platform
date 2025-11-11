import { Trash2, Square, BarChart2, Users } from 'lucide-react'
import StatusBadge from '../common/StatusBadge'
import { SCENARIO_TYPES } from '../../utils/constants'
import { fmtRelative, fmtRps, fmtPct, fmtDuration } from '../../utils/formatters'

export default function TestCard({ test, onDelete, onStop, onView }) {
  const {
    test_id, name, scenario_type, status,
    virtual_users, duration_seconds, created_at, started_at,
    summary,
  } = test

  const scenarioInfo = SCENARIO_TYPES[scenario_type] || { label: scenario_type, color: 'text-gray-400' }
  const isRunning = status === 'running'

  return (
    <div className="card hover:border-gray-600 transition-colors">
      <div className="flex items-start justify-between mb-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-gray-100 truncate">{name}</p>
          <p className={`text-xs mt-0.5 ${scenarioInfo.color}`}>
            {scenarioInfo.label} scenario
          </p>
        </div>
        <StatusBadge status={status} className="shrink-0 ml-2" />
      </div>

      <div className="flex items-center gap-3 text-xs text-gray-400 mb-3">
        <span className="flex items-center gap-1">
          <Users size={12} />
          {virtual_users ?? '—'} VU
        </span>
        <span>·</span>
        <span>{fmtDuration(duration_seconds)}</span>
      </div>

      {summary && (
        <div className="grid grid-cols-2 gap-2 mb-3">
          <div className="bg-gray-700 rounded-lg p-2 text-center">
            <p className="text-xs text-gray-500">Peak RPS</p>
            <p className="text-sm font-semibold text-blue-400">{fmtRps(summary.peak_rps)}</p>
          </div>
          <div className="bg-gray-700 rounded-lg p-2 text-center">
            <p className="text-xs text-gray-500">Error rate</p>
            <p className={`text-sm font-semibold ${(summary.error_rate_pct ?? 0) > 5 ? 'text-red-400' : 'text-green-400'}`}>
              {fmtPct(summary.error_rate_pct)}
            </p>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-600">{fmtRelative(started_at || created_at)}</span>
        <div className="flex items-center gap-1">
          <button onClick={() => onView?.(test_id)} className="btn-ghost px-2 py-1 text-xs" title="View">
            <BarChart2 size={14} />
          </button>
          {isRunning && (
            <button onClick={() => onStop?.(test_id)} className="btn-ghost px-2 py-1 text-xs text-yellow-400 hover:bg-yellow-900/30" title="Stop">
              <Square size={14} />
            </button>
          )}
          {!isRunning && (
            <button onClick={() => onDelete?.(test_id)} className="btn-ghost px-2 py-1 text-xs text-red-400 hover:bg-red-900/30" title="Delete">
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
