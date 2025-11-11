import { Plus, RefreshCw } from 'lucide-react'
import TestCard from './TestCard'
import LoadingSpinner from '../common/LoadingSpinner'
import { SCENARIO_TYPES } from '../../utils/constants'

const STATUSES = ['all', 'pending', 'running', 'completed', 'failed', 'stopped']

export default function TestList({ tests, loading, filter, onFilterChange, onNew, onDelete, onStop, onView, onRefresh }) {
  const filtered = tests.filter((t) => filter === 'all' || t.status === filter)

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <select
          className="select w-auto text-sm"
          value={filter}
          onChange={(e) => onFilterChange(e.target.value)}
        >
          {STATUSES.map((s) => <option key={s} value={s}>{s === 'all' ? 'All statuses' : s}</option>)}
        </select>

        <div className="flex-1" />

        <button onClick={onRefresh} className="btn-ghost flex items-center gap-1.5 text-sm">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>

        <button onClick={onNew} className="btn-primary flex items-center gap-1.5 text-sm">
          <Plus size={14} />
          New Test
        </button>
      </div>

      {loading && !filtered.length
        ? <LoadingSpinner fullscreen label="Loading tests…" />
        : filtered.length === 0
          ? (
            <div className="card text-center py-12 text-gray-500">
              <p className="text-sm">No tests found. Start your first load test!</p>
            </div>
          )
          : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {filtered.map((test) => (
                <TestCard key={test.test_id} test={test} onDelete={onDelete} onStop={onStop} onView={onView} />
              ))}
            </div>
          )
      }
    </div>
  )
}
