import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { ERROR_RATE_THRESHOLD_PCT } from '../../utils/constants'

const TOOLTIP_STYLE = {
  backgroundColor: '#1F2937',
  border: '1px solid #374151',
  color: '#F9FAFB',
  fontSize: 12,
}

export default function ErrorRateChart({ data = [], threshold = ERROR_RATE_THRESHOLD_PCT, height = 220 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="errGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#EF4444" stopOpacity={0.4} />
            <stop offset="95%" stopColor="#EF4444" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
        <XAxis dataKey="time" stroke="#6B7280" tick={{ fontSize: 11 }} />
        <YAxis stroke="#6B7280" tick={{ fontSize: 11 }} unit="%" domain={[0, 'auto']} width={44} />
        <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [`${v.toFixed(2)}%`, 'Error Rate']} />
        <ReferenceLine
          y={threshold} stroke="#EF4444" strokeDasharray="5 3"
          label={{ value: `${threshold}% SLO`, fill: '#EF4444', fontSize: 11, position: 'insideTopRight' }}
        />
        <Area type="monotone" dataKey="error_rate" name="Error Rate"
          stroke="#EF4444" fill="url(#errGrad)" strokeWidth={2} dot={false} />
      </AreaChart>
    </ResponsiveContainer>
  )
}
