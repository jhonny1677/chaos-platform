import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts'

const TOOLTIP_STYLE = {
  backgroundColor: '#1F2937',
  border: '1px solid #374151',
  color: '#F9FAFB',
  fontSize: 12,
}

export default function LatencyChart({ data = [], height = 280 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
        <XAxis dataKey="time" stroke="#6B7280" tick={{ fontSize: 11 }} />
        <YAxis stroke="#6B7280" tick={{ fontSize: 11 }} unit="ms" width={52} />
        <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [`${Math.round(v)}ms`]} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line type="monotone" dataKey="p50" name="p50"  stroke="#60A5FA" dot={false} strokeWidth={1.5} />
        <Line type="monotone" dataKey="p95" name="p95"  stroke="#FBBF24" dot={false} strokeWidth={1.5} />
        <Line type="monotone" dataKey="p99" name="p99"  stroke="#F87171" dot={false} strokeWidth={2} />
        <Line type="monotone" dataKey="mean" name="avg" stroke="#A78BFA" dot={false} strokeWidth={1} strokeDasharray="4 2" />
      </LineChart>
    </ResponsiveContainer>
  )
}
