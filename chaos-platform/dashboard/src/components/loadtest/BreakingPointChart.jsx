import {
  ComposedChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Legend,
} from 'recharts'

const TOOLTIP_STYLE = {
  backgroundColor: '#1F2937',
  border: '1px solid #374151',
  color: '#F9FAFB',
  fontSize: 12,
}

export default function BreakingPointChart({ data = [], breakingPoint, height = 300 }) {
  if (!data.length) return (
    <div className="flex items-center justify-center h-32 text-gray-500 text-sm">
      No stress test data. Run a stress scenario to find the breaking point.
    </div>
  )

  return (
    <div>
      {breakingPoint && (
        <p className="text-sm text-yellow-400 mb-3">
          Breaking point detected at <span className="font-bold">{breakingPoint} virtual users</span>
        </p>
      )}
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={data} margin={{ top: 4, right: 40, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis dataKey="virtual_users" stroke="#6B7280" tick={{ fontSize: 11 }} label={{ value: 'Virtual Users', position: 'insideBottom', offset: -4, fill: '#6B7280', fontSize: 11 }} />
          <YAxis yAxisId="rps" orientation="left"  stroke="#60A5FA" tick={{ fontSize: 11 }} unit=" r/s" width={52} />
          <YAxis yAxisId="err" orientation="right" stroke="#EF4444" tick={{ fontSize: 11 }} unit="%" width={40} />
          <Tooltip contentStyle={TOOLTIP_STYLE} />
          <Legend wrapperStyle={{ fontSize: 12 }} />

          {breakingPoint && (
            <ReferenceLine yAxisId="rps" x={breakingPoint} stroke="#FBBF24" strokeDasharray="5 3"
              label={{ value: 'Breaking point', fill: '#FBBF24', fontSize: 11, position: 'top' }} />
          )}

          <Line yAxisId="rps" type="monotone" dataKey="rps"
            name="RPS" stroke="#60A5FA" strokeWidth={2} dot={{ r: 3 }} />
          <Line yAxisId="err" type="monotone" dataKey="error_rate_pct"
            name="Error %" stroke="#EF4444" strokeWidth={2} dot={{ r: 3 }} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
