import { Server, RefreshCw } from 'lucide-react'
import { clsx } from '../../utils/helpers'

function PodBadge({ pod }) {
  const isReady = pod.ready
  return (
    <div className={clsx(
      'flex items-start gap-2 p-3 rounded-lg border transition-colors',
      isReady ? 'bg-green-900/20 border-green-800' : 'bg-red-900/20 border-red-800'
    )}>
      <Server size={14} className={isReady ? 'text-green-400 mt-0.5' : 'text-red-400 mt-0.5'} />
      <div className="min-w-0">
        <p className="text-xs font-mono text-gray-200 truncate">{pod.name}</p>
        <div className="flex items-center gap-2 mt-1">
          <span className={clsx('text-xs', isReady ? 'text-green-400' : 'text-red-400')}>
            {pod.phase}
          </span>
          {pod.restarts > 0 && (
            <span className="text-xs text-yellow-400">{pod.restarts} restart{pod.restarts > 1 ? 's' : ''}</span>
          )}
        </div>
      </div>
    </div>
  )
}

export default function PodHealth({ pods = [], loading, onRefresh }) {
  const ready   = pods.filter((p) => p.ready).length
  const total   = pods.length
  const healthy = total > 0 && ready === total

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-100">Pod Health</h3>
          <p className={clsx('text-xs mt-0.5', healthy ? 'text-green-400' : 'text-yellow-400')}>
            {ready}/{total} ready
          </p>
        </div>
        <button onClick={onRefresh} className="btn-ghost p-1" title="Refresh pods">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {pods.length === 0 ? (
        <p className="text-xs text-gray-500">No pods found — is Prometheus reachable?</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {pods.map((pod) => <PodBadge key={pod.name} pod={pod} />)}
        </div>
      )}
    </div>
  )
}
