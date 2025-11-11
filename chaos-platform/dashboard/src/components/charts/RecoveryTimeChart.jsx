import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import { truncate } from '../../utils/helpers'

const TOOLTIP_STYLE = {
  backgroundColor: '#1F2937',
  border: '1px solid #374151',
  color: '#F9FAFB',
  fontSize: 12,
}

const barColor = (seconds) => {
  if (seconds < 30) return '#22C55E'
  if (seconds < 120) return '#FBBF24'
  return '#EF4444'
}

export default function RecoveryTimeChart({ data = [], height = 260 }) {
  if (!data.length) return (
    <div className="flex items-center justify-center h-40 text-gray-500 text-sm">No recovery data yet</div>
  )

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 32 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
        <XAxis
          dataKey="name" stroke="#6B7280" tick={{ fontSize: 10 }}
          angle={-30} textAnchor="end"
          tickFormatter={(v) => truncate(v, 16)}
        />
        <YAxis stroke="#6B7280" tick={{ fontSize: 11 }} unit="s" width={44} />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          formatter={(v) => [`${v.toFixed(1)}s`, 'Recovery time']}
        />
        <Bar dataKey="recovery_time_seconds" name="Recovery" radius={[4, 4, 0, 0]}>
          {data.map((entry, i) => (
            <Cell key={i} fill={barColor(entry.recovery_time_seconds)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
