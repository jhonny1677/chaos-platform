import { Trash2, Eye, Zap } from 'lucide-react'
import StatusBadge from '../common/StatusBadge'
import { CHAOS_TYPES } from '../../utils/constants'
import { fmtRelative, fmtDuration } from '../../utils/formatters'

export default function ExperimentCard({ experiment, onDelete, onView }) {
  const {
    experiment_id, name, chaos_type, status,
    target_namespace, created_at, started_at,
    result_summary,
  } = experiment

  const typeInfo = CHAOS_TYPES[chaos_type] || { label: chaos_type, color: 'text-gray-400' }
  const recovered = result_summary?.all_recovered

  return (
    <div className="card hover:border-gray-600 transition-colors">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-start gap-2 min-w-0">
          <Zap size={16} className={`${typeInfo.color} mt-0.5 shrink-0`} />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-gray-100 truncate">{name}</p>
            <p className="text-xs text-gray-500 mt-0.5">{typeInfo.label} · {target_namespace}</p>
          </div>
        </div>
        <StatusBadge status={status} className="shrink-0 ml-2" />
      </div>

      {result_summary && (
        <div className="grid grid-cols-3 gap-2 mb-3 text-center">
          <div className="bg-gray-700 rounded-lg p-2">
            <p className="text-xs text-gray-500">Error rate</p>
            <p className="text-sm font-semibold text-gray-200">
              {result_summary.error_rate_during?.toFixed(1) ?? '—'}%
            </p>
          </div>
          <div className="bg-gray-700 rounded-lg p-2">
            <p className="text-xs text-gray-500">Recovery</p>
            <p className="text-sm font-semibold text-gray-200">
              {fmtDuration(result_summary.recovery_time_seconds)}
            </p>
          </div>
          <div className="bg-gray-700 rounded-lg p-2">
            <p className="text-xs text-gray-500">Recovered</p>
            <p className={`text-sm font-semibold ${recovered ? 'text-green-400' : 'text-red-400'}`}>
              {recovered === undefined ? '—' : recovered ? 'Yes' : 'No'}
            </p>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-600">{fmtRelative(started_at || created_at)}</span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => onView?.(experiment_id)}
            className="btn-ghost px-2 py-1 text-xs"
            title="View details"
          >
            <Eye size={14} />
          </button>
          {status !== 'running' && (
            <button
              onClick={() => onDelete?.(experiment_id)}
              className="btn-ghost px-2 py-1 text-xs text-red-400 hover:text-red-300 hover:bg-red-900/30"
              title="Delete"
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
