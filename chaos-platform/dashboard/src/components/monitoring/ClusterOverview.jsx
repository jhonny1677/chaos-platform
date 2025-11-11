import { CheckCircle2, AlertTriangle, XCircle, Layers } from 'lucide-react'
import { useSelector } from 'react-redux'
import { selectPods, selectKilledPods } from '../../store/slices/metricsSlice'
import { selectExperiments } from '../../store/slices/experimentsSlice'
import { selectActiveTests } from '../../store/slices/loadTestsSlice'
import { fmtRelative } from '../../utils/formatters'

function OverviewRow({ label, value, color = 'text-gray-200' }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-gray-700 last:border-0">
      <span className="text-sm text-gray-400">{label}</span>
      <span className={`text-sm font-semibold ${color}`}>{value}</span>
    </div>
  )
}

export default function ClusterOverview() {
  const pods        = useSelector(selectPods)
  const killedPods  = useSelector(selectKilledPods)
  const experiments = useSelector(selectExperiments)
  const activeTests = useSelector(selectActiveTests)

  const readyPods      = pods.filter((p) => p.ready).length
  const totalPods      = pods.length
  const restartingPods = pods.filter((p) => p.restarts > 0).length
  const runningExp     = experiments.filter((e) => e.status === 'running').length
  const clusterHealthy = totalPods > 0 && readyPods === totalPods && restartingPods === 0

  const Icon = clusterHealthy ? CheckCircle2 : restartingPods > 0 ? AlertTriangle : XCircle
  const iconColor = clusterHealthy ? 'text-green-400' : restartingPods > 0 ? 'text-yellow-400' : 'text-red-400'
  const statusText = clusterHealthy ? 'All systems healthy' : `${restartingPods} pods restarting`

  return (
    <div className="card space-y-3">
      <div className="flex items-center gap-2">
        <Layers size={16} className="text-blue-400" />
        <h3 className="text-sm font-semibold text-gray-100">Cluster Overview</h3>
      </div>

      <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-700">
        <Icon size={16} className={iconColor} />
        <span className={`text-sm font-medium ${iconColor}`}>{statusText}</span>
      </div>

      <div>
        <OverviewRow label="Ready pods"         value={`${readyPods} / ${totalPods}`} color={readyPods === totalPods ? 'text-green-400' : 'text-red-400'} />
        <OverviewRow label="Restarting pods"    value={restartingPods} color={restartingPods > 0 ? 'text-yellow-400' : 'text-gray-300'} />
        <OverviewRow label="Running experiments" value={runningExp}    color={runningExp > 0 ? 'text-red-400' : 'text-gray-300'} />
        <OverviewRow label="Active load tests"  value={activeTests.length} color={activeTests.length > 0 ? 'text-blue-400' : 'text-gray-300'} />
        <OverviewRow label="Pods killed today"  value={killedPods.length} color={killedPods.length > 0 ? 'text-orange-400' : 'text-gray-300'} />
      </div>

      {killedPods.length > 0 && (
        <div className="mt-2">
          <p className="text-xs text-gray-500 mb-2">Recently killed</p>
          <ul className="space-y-1">
            {killedPods.slice(0, 5).map((kp, i) => (
              <li key={i} className="flex items-center justify-between text-xs">
                <span className="font-mono text-red-300 truncate">{kp.pod_name}</span>
                <span className="text-gray-600 ml-2 shrink-0">{fmtRelative(kp.killed_at)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
