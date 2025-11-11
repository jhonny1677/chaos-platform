import { CheckCircle2, XCircle, MinusCircle } from 'lucide-react'
import { fmtPct, fmtMs } from '../../utils/formatters'

function Row({ label, before, during, after, unit = '', threshold }) {
  const overThreshold = threshold !== undefined && after > threshold
  return (
    <tr className="border-b border-gray-700">
      <td className="py-2 pr-4 text-xs text-gray-400 whitespace-nowrap">{label}</td>
      <td className="py-2 pr-4 text-xs text-gray-300 text-right">{before}{unit}</td>
      <td className="py-2 pr-4 text-xs text-red-300 text-right font-medium">{during}{unit}</td>
      <td className={`py-2 text-xs text-right font-medium ${overThreshold ? 'text-red-400' : 'text-green-400'}`}>
        {after}{unit}
      </td>
    </tr>
  )
}

export default function HypothesisResult({ result }) {
  if (!result) return <p className="text-sm text-gray-500">No result data available.</p>

  const passed = result.hypothesis_passed
  const h = result.hypothesis_result ?? {}

  return (
    <div className="space-y-4">
      {/* Pass / fail banner */}
      <div className={`flex items-center gap-2 px-4 py-3 rounded-lg border ${
        passed === true  ? 'bg-green-900/40 border-green-700 text-green-300' :
        passed === false ? 'bg-red-900/40 border-red-700 text-red-300' :
                          'bg-gray-700 border-gray-600 text-gray-300'
      }`}>
        {passed === true  && <CheckCircle2 size={18} />}
        {passed === false && <XCircle size={18} />}
        {passed === null  && <MinusCircle size={18} />}
        <span className="text-sm font-semibold">
          {passed === true ? 'Steady state MAINTAINED' :
           passed === false ? 'Steady state VIOLATED' :
           'Hypothesis not checked'}
        </span>
      </div>

      {/* Before / during / after metrics table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-700">
              <th className="pb-2 text-xs text-gray-500 text-left">Metric</th>
              <th className="pb-2 text-xs text-gray-500 text-right">Before</th>
              <th className="pb-2 text-xs text-gray-500 text-right">During</th>
              <th className="pb-2 text-xs text-gray-500 text-right">After</th>
            </tr>
          </thead>
          <tbody>
            <Row label="Error rate"
              before={fmtPct(result.error_rate_before)}
              during={fmtPct(result.error_rate_during)}
              after={fmtPct(result.error_rate_after)}
              threshold={h.error_rate_threshold}
            />
            <Row label="Latency p99"
              before={fmtMs(result.latency_p99_before_ms)}
              during={fmtMs(result.peak_latency_ms)}
              after={fmtMs(result.latency_p99_after_ms)}
              threshold={h.latency_threshold}
            />
          </tbody>
        </table>
      </div>

      {h.error && (
        <p className="text-xs text-red-400 bg-red-900/20 p-2 rounded">{h.error}</p>
      )}
    </div>
  )
}
