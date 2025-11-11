import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { clsx } from '../../utils/helpers'

export default function MetricCard({ title, value, subtitle, icon: Icon, trend, accentClass = 'text-blue-400' }) {
  const Trend = trend > 0 ? TrendingUp : trend < 0 ? TrendingDown : Minus
  const trendColor = trend > 0 ? 'text-green-400' : trend < 0 ? 'text-red-400' : 'text-gray-500'

  return (
    <div className="card flex flex-col gap-3">
      <div className="flex items-start justify-between">
        <span className="text-sm text-gray-400 font-medium">{title}</span>
        {Icon && <Icon size={18} className={accentClass} />}
      </div>
      <div className="flex items-end justify-between">
        <span className={clsx('text-2xl font-bold', accentClass)}>{value}</span>
        {trend !== undefined && (
          <Trend size={16} className={trendColor} />
        )}
      </div>
      {subtitle && <span className="text-xs text-gray-500">{subtitle}</span>}
    </div>
  )
}
