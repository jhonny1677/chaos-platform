import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, ResponsiveContainer, Legend,
} from 'recharts'

const TOOLTIP_STYLE = {
  backgroundColor: '#1F2937',
  border: '1px solid #374151',
  color: '#F9FAFB',
  fontSize: 12,
}

export default function TimelineChart({ data = [], events = [], height = 300 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="errTLGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#EF4444" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#EF4444" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
        <XAxis dataKey="time" stroke="#6B7280" tick={{ fontSize: 11 }} />
        <YAxis yAxisId="latency" orientation="left"  stroke="#60A5FA" tick={{ fontSize: 11 }} unit="ms" width={52} />
        <YAxis yAxisId="error"   orientation="right" stroke="#EF4444" tick={{ fontSize: 11 }} unit="%" width={40} />
        <Tooltip contentStyle={TOOLTIP_STYLE} />
        <Legend wrapperStyle={{ fontSize: 12 }} />

        {/* Chaos event markers */}
        {events.map((ev, i) => (
          <ReferenceLine
            key={i} yAxisId="latency" x={ev.time}
            stroke={ev.type === 'chaos_start' ? '#EF4444' : '#22C55E'}
            strokeDasharray="4 2"
            label={{ value: ev.label, fill: ev.type === 'chaos_start' ? '#FCA5A5' : '#86EFAC', fontSize: 10, position: 'top' }}
          />
        ))}

        <Area yAxisId="error" type="monotone" dataKey="error_rate"
          name="Error %" stroke="#EF4444" fill="url(#errTLGrad)" strokeWidth={1.5} dot={false} />
        <Line yAxisId="latency" type="monotone" dataKey="p99"
          name="p99 (ms)" stroke="#60A5FA" strokeWidth={2} dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
