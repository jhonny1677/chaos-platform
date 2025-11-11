import { useEffect, useRef } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { Zap, Activity, CheckCircle2, AlertTriangle } from 'lucide-react'
import MetricCard from '../components/common/MetricCard'
import RequestRateChart from '../components/charts/RequestRateChart'
import ErrorRateChart from '../components/charts/ErrorRateChart'
import ExperimentCard from '../components/chaos/ExperimentCard'
import TestCard from '../components/loadtest/TestCard'
import LoadingSpinner from '../components/common/LoadingSpinner'
import { fetchExperiments, selectExperiments } from '../store/slices/experimentsSlice'
import { fetchTests, selectTests, selectActiveTests } from '../store/slices/loadTestsSlice'
import { selectRateData } from '../store/slices/metricsSlice'
import * as metricsApi from '../services/metricsApi'
import { setRequestRateData, setErrorRateData } from '../store/slices/metricsSlice'
import { REFRESH_INTERVAL_MS } from '../utils/constants'
import { fmtRps, fmtPct } from '../utils/formatters'

function parseRangeResult(result, key) {
  return (result ?? []).map(([ts, val]) => ({
    time: new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    [key]: parseFloat(val) || 0,
  }))
}

export default function Dashboard() {
  const dispatch = useDispatch()
  const experiments = useSelector(selectExperiments)
  const tests       = useSelector(selectTests)
  const activeTests = useSelector(selectActiveTests)
  const { request: rpsData, error: errData } = useSelector(selectRateData)

  const loading = !experiments.length && !tests.length

  const fetchAll = async () => {
    dispatch(fetchExperiments())
    dispatch(fetchTests())
    try {
      const [rps, err] = await Promise.all([
        metricsApi.fetchRequestRate('target-app', 5),
        metricsApi.fetchErrorRate('target-app', 5),
      ])
      const rpsValues = rps.data?.data?.result?.[0]?.values ?? []
      const errValues = err.data?.data?.result?.[0]?.values ?? []
      dispatch(setRequestRateData(parseRangeResult(rpsValues, 'rps')))
      dispatch(setErrorRateData(parseRangeResult(errValues, 'error_rate')))
    } catch { /* Prometheus may be unavailable */ }
  }

  useEffect(() => {
    fetchAll()
    const timer = setInterval(fetchAll, REFRESH_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [])

  const runningExps  = experiments.filter((e) => e.status === 'running').length
  const completedExp = experiments.filter((e) => e.status === 'completed').length
  const failedExp    = experiments.filter((e) => e.status === 'failed').length
  const latestRps    = rpsData[rpsData.length - 1]?.rps ?? null
  const latestErr    = errData[errData.length - 1]?.error_rate ?? null

  return (
    <div className="space-y-6">
      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard title="Active experiments" value={runningExps}      icon={Zap}          accentClass="text-red-400" />
        <MetricCard title="Active load tests"  value={activeTests.length} icon={Activity}   accentClass="text-blue-400" />
        <MetricCard title="Completed chaos"    value={completedExp}    icon={CheckCircle2}   accentClass="text-green-400" />
        <MetricCard title="Failed experiments" value={failedExp}       icon={AlertTriangle}  accentClass="text-yellow-400" />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <h2 className="section-title mb-0">Request Rate</h2>
            {latestRps !== null && <span className="text-sm font-semibold text-blue-400">{fmtRps(latestRps)}</span>}
          </div>
          <RequestRateChart data={rpsData} height={200} />
        </div>
        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <h2 className="section-title mb-0">Error Rate</h2>
            {latestErr !== null && (
              <span className={`text-sm font-semibold ${latestErr > 5 ? 'text-red-400' : 'text-green-400'}`}>
                {fmtPct(latestErr)}
              </span>
            )}
          </div>
          <ErrorRateChart data={errData} height={200} />
        </div>
      </div>

      {/* Recent activity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div>
          <h2 className="section-title">Recent Experiments</h2>
          {loading ? <LoadingSpinner /> : experiments.length === 0
            ? <p className="text-sm text-gray-500">No experiments yet.</p>
            : <div className="space-y-3">
                {experiments.slice(0, 4).map((exp) => (
                  <ExperimentCard key={exp.experiment_id} experiment={exp} />
                ))}
              </div>
          }
        </div>
        <div>
          <h2 className="section-title">Recent Load Tests</h2>
          {loading ? <LoadingSpinner /> : tests.length === 0
            ? <p className="text-sm text-gray-500">No load tests yet.</p>
            : <div className="space-y-3">
                {tests.slice(0, 4).map((test) => (
                  <TestCard key={test.test_id} test={test} />
                ))}
              </div>
          }
        </div>
      </div>
    </div>
  )
}
