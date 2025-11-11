import { useSelector } from 'react-redux'
import PodHealth from '../components/monitoring/PodHealth'
import ClusterOverview from '../components/monitoring/ClusterOverview'
import AlertsList from '../components/monitoring/AlertsList'
import RequestRateChart from '../components/charts/RequestRateChart'
import ErrorRateChart from '../components/charts/ErrorRateChart'
import TimelineChart from '../components/charts/TimelineChart'
import LoadingSpinner from '../components/common/LoadingSpinner'
import { useMetrics } from '../hooks/useMetrics'
import { selectPods, selectAlerts, selectRateData } from '../store/slices/metricsSlice'
import { selectKilledPods } from '../store/slices/metricsSlice'

export default function Monitoring() {
  const { loading, refresh } = useMetrics('target-app')
  const pods       = useSelector(selectPods)
  const alerts     = useSelector(selectAlerts)
  const killedPods = useSelector(selectKilledPods)
  const { request: rpsData, error: errData } = useSelector(selectRateData)

  // Build timeline events from killed pods
  const chaosEvents = killedPods.slice(0, 20).map((kp) => ({
    time: new Date(kp.killed_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    type: 'chaos_start',
    label: kp.pod_name ? kp.pod_name.split('-').pop() : 'pod',
  }))

  return (
    <div className="space-y-6">
      {/* Top row — overview + alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-1">
          <ClusterOverview />
        </div>
        <div className="lg:col-span-2 card overflow-y-auto max-h-72">
          <h2 className="section-title">Active Alerts</h2>
          <AlertsList alerts={alerts} />
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card">
          <h2 className="section-title">Request Rate (5m)</h2>
          <RequestRateChart data={rpsData} height={200} />
        </div>
        <div className="card">
          <h2 className="section-title">Error Rate (5m)</h2>
          <ErrorRateChart data={errData} height={200} />
        </div>
      </div>

      {/* Chaos-correlated timeline */}
      {(rpsData.length > 0 || chaosEvents.length > 0) && (
        <div className="card">
          <h2 className="section-title">Chaos Correlation Timeline</h2>
          <TimelineChart
            data={rpsData.map((d, i) => ({ ...d, error_rate: errData[i]?.error_rate ?? 0, p99: 0 }))}
            events={chaosEvents}
            height={280}
          />
        </div>
      )}

      {/* Pod health */}
      <PodHealth pods={pods} loading={loading} onRefresh={refresh} />
    </div>
  )
}
