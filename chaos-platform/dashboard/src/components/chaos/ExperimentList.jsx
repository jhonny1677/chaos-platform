import { Plus, RefreshCw } from 'lucide-react'
import ExperimentCard from './ExperimentCard'
import LoadingSpinner from '../common/LoadingSpinner'
import { CHAOS_TYPES } from '../../utils/constants'

const STATUSES = ['all', 'pending', 'running', 'completed', 'failed', 'aborted']

export default function ExperimentList({ experiments, loading, filters, onFilterChange, onNew, onDelete, onView, onRefresh }) {
  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-3 flex-wrap">
        <select
          className="select w-auto text-sm"
          value={filters.status}
          onChange={(e) => onFilterChange({ status: e.target.value })}
        >
          {STATUSES.map((s) => <option key={s} value={s}>{s === 'all' ? 'All statuses' : s}</option>)}
        </select>

        <select
          className="select w-auto text-sm"
          value={filters.type}
          onChange={(e) => onFilterChange({ type: e.target.value })}
        >
          <option value="all">All types</option>
          {Object.entries(CHAOS_TYPES).map(([k, v]) => (
            <option key={k} value={k}>{v.label}</option>
          ))}
        </select>

        <div className="flex-1" />

        <button onClick={onRefresh} className="btn-ghost flex items-center gap-1.5 text-sm" title="Refresh">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>

        <button onClick={onNew} className="btn-primary flex items-center gap-1.5 text-sm">
          <Plus size={14} />
          New Experiment
        </button>
      </div>

      {/* Content */}
      {loading && !experiments.length
        ? <LoadingSpinner fullscreen label="Loading experiments…" />
        : experiments.length === 0
          ? (
            <div className="card text-center py-12 text-gray-500">
              <p className="text-sm">No experiments found. Run your first chaos experiment!</p>
            </div>
          )
          : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {experiments.map((exp) => (
                <ExperimentCard
                  key={exp.experiment_id}
                  experiment={exp}
                  onDelete={onDelete}
                  onView={onView}
                />
              ))}
            </div>
          )
      }
    </div>
  )
}
