import { useState, useEffect } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { Download, RefreshCw } from 'lucide-react'
import { fetchExperiments, selectExperiments } from '../store/slices/experimentsSlice'
import { fetchTests, selectTests } from '../store/slices/loadTestsSlice'
import StatusBadge from '../components/common/StatusBadge'
import RecoveryTimeChart from '../components/charts/RecoveryTimeChart'
import BreakingPointChart from '../components/loadtest/BreakingPointChart'
import HypothesisResult from '../components/chaos/HypothesisResult'
import { fmtDate, fmtDuration, fmtMs, fmtPct, fmtRps } from '../utils/formatters'
import { CHAOS_TYPES, SCENARIO_TYPES } from '../utils/constants'
import { downloadJson } from '../utils/helpers'

export default function Results() {
  const dispatch = useDispatch()
  const experiments = useSelector(selectExperiments)
  const tests = useSelector(selectTests)
  const [tab, setTab] = useState('chaos')
  const [selectedExp, setSelectedExp] = useState(null)

  useEffect(() => {
    dispatch(fetchExperiments())
    dispatch(fetchTests())
  }, [dispatch])

  // Recovery time chart data from completed experiments
  const recoveryData = experiments
    .filter((e) => e.status === 'completed' && e.result_summary?.recovery_time_seconds != null)
    .map((e) => ({ name: e.name, recovery_time_seconds: e.result_summary.recovery_time_seconds }))

  // Breaking point data from completed stress tests
  const stressTests = tests.filter((t) => t.scenario_type === 'stress' && t.status === 'completed')
  const breakingData = stressTests[0]?.summary?.step_data ?? []
  const breakingPoint = stressTests[0]?.summary?.breaking_point_users

  const refresh = () => { dispatch(fetchExperiments()); dispatch(fetchTests()) }

  return (
    <div className="space-y-6">
      {/* Tabs */}
      <div className="flex items-center justify-between">
        <div className="flex gap-1 bg-gray-800 rounded-lg p-1">
          {['chaos', 'loadtest'].map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${tab === t ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-gray-200'}`}>
              {t === 'chaos' ? 'Chaos Results' : 'Load Test Results'}
            </button>
          ))}
        </div>
        <button onClick={refresh} className="btn-ghost flex items-center gap-1.5 text-sm">
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {tab === 'chaos' && (
        <div className="space-y-6">
          {/* Recovery time chart */}
          {recoveryData.length > 0 && (
            <div className="card">
              <h2 className="section-title">Recovery Times</h2>
              <RecoveryTimeChart data={recoveryData} />
            </div>
          )}

          {/* Experiments table */}
          <div className="card overflow-x-auto">
            <h2 className="section-title">All Experiments</h2>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700 text-left">
                  {['Name', 'Type', 'Namespace', 'Status', 'Hypothesis', 'Recovery', 'Date'].map((h) => (
                    <th key={h} className="pb-3 pr-4 text-xs font-medium text-gray-500 uppercase tracking-wide">{h}</th>
                  ))}
                  <th className="pb-3" />
                </tr>
              </thead>
              <tbody>
                {experiments.length === 0 && (
                  <tr><td colSpan={8} className="py-6 text-center text-gray-500 text-sm">No experiments yet</td></tr>
                )}
                {experiments.map((exp) => (
                  <tr key={exp.experiment_id} className="border-b border-gray-700/50 hover:bg-gray-700/30 cursor-pointer" onClick={() => setSelectedExp(selectedExp?.experiment_id === exp.experiment_id ? null : exp)}>
                    <td className="py-3 pr-4 text-gray-200 font-medium">{exp.name}</td>
                    <td className="py-3 pr-4 text-gray-400">{CHAOS_TYPES[exp.chaos_type]?.label || exp.chaos_type}</td>
                    <td className="py-3 pr-4 text-gray-400 font-mono text-xs">{exp.target_namespace}</td>
                    <td className="py-3 pr-4"><StatusBadge status={exp.status} /></td>
                    <td className="py-3 pr-4">
                      {exp.result_summary?.hypothesis_passed === true && <span className="text-green-400 text-xs font-medium">PASSED</span>}
                      {exp.result_summary?.hypothesis_passed === false && <span className="text-red-400 text-xs font-medium">FAILED</span>}
                      {exp.result_summary?.hypothesis_passed == null && <span className="text-gray-600 text-xs">—</span>}
                    </td>
                    <td className="py-3 pr-4 text-gray-400">{fmtDuration(exp.result_summary?.recovery_time_seconds)}</td>
                    <td className="py-3 pr-4 text-gray-500 text-xs">{fmtDate(exp.created_at)}</td>
                    <td className="py-3">
                      <button onClick={(e) => { e.stopPropagation(); downloadJson(exp, `${exp.name}.json`) }} className="btn-ghost p-1" title="Download">
                        <Download size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Selected experiment detail */}
          {selectedExp && (
            <div className="card">
              <h2 className="section-title">Hypothesis Detail — {selectedExp.name}</h2>
              <HypothesisResult result={selectedExp.result_summary} />
            </div>
          )}
        </div>
      )}

      {tab === 'loadtest' && (
        <div className="space-y-6">
          {/* Breaking point chart */}
          <div className="card">
            <h2 className="section-title">Breaking Point Analysis</h2>
            <BreakingPointChart data={breakingData} breakingPoint={breakingPoint} />
          </div>

          {/* Tests table */}
          <div className="card overflow-x-auto">
            <h2 className="section-title">All Load Tests</h2>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700 text-left">
                  {['Name', 'Scenario', 'Status', 'Peak RPS', 'Error %', 'Duration', 'Date'].map((h) => (
                    <th key={h} className="pb-3 pr-4 text-xs font-medium text-gray-500 uppercase tracking-wide">{h}</th>
                  ))}
                  <th className="pb-3" />
                </tr>
              </thead>
              <tbody>
                {tests.length === 0 && (
                  <tr><td colSpan={8} className="py-6 text-center text-gray-500 text-sm">No tests yet</td></tr>
                )}
                {tests.map((t) => (
                  <tr key={t.test_id} className="border-b border-gray-700/50">
                    <td className="py-3 pr-4 text-gray-200 font-medium">{t.name}</td>
                    <td className="py-3 pr-4 text-gray-400">{SCENARIO_TYPES[t.scenario_type]?.label || t.scenario_type}</td>
                    <td className="py-3 pr-4"><StatusBadge status={t.status} /></td>
                    <td className="py-3 pr-4 text-gray-400">{fmtRps(t.summary?.peak_rps)}</td>
                    <td className="py-3 pr-4">
                      <span className={(t.summary?.error_rate_pct ?? 0) > 5 ? 'text-red-400' : 'text-green-400'}>
                        {fmtPct(t.summary?.error_rate_pct)}
                      </span>
                    </td>
                    <td className="py-3 pr-4 text-gray-400">{fmtDuration(t.duration_seconds)}</td>
                    <td className="py-3 pr-4 text-gray-500 text-xs">{fmtDate(t.created_at)}</td>
                    <td className="py-3">
                      <button onClick={() => downloadJson(t, `${t.name}.json`)} className="btn-ghost p-1" title="Download">
                        <Download size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
