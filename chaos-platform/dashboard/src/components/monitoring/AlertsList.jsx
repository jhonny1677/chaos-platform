import { Bell, AlertTriangle, Info } from 'lucide-react'
import { fmtRelative } from '../../utils/formatters'
import { clsx } from '../../utils/helpers'

const SEVERITY_MAP = {
  critical: { Icon: AlertTriangle, color: 'text-red-400',    bg: 'bg-red-900/20 border-red-800' },
  warning:  { Icon: AlertTriangle, color: 'text-yellow-400', bg: 'bg-yellow-900/20 border-yellow-800' },
  info:     { Icon: Info,          color: 'text-blue-400',   bg: 'bg-blue-900/20 border-blue-800' },
}

export default function AlertsList({ alerts = [] }) {
  if (!alerts.length) {
    return (
      <div className="card text-center py-6">
        <Bell size={20} className="mx-auto mb-2 text-gray-600" />
        <p className="text-sm text-gray-500">No active alerts</p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {alerts.map((alert, i) => {
        const severity = alert.labels?.severity || 'info'
        const { Icon, color, bg } = SEVERITY_MAP[severity] || SEVERITY_MAP.info
        return (
          <div key={i} className={clsx('flex items-start gap-3 p-3 rounded-lg border', bg)}>
            <Icon size={16} className={`${color} mt-0.5 shrink-0`} />
            <div className="min-w-0">
              <p className={clsx('text-xs font-semibold', color)}>
                {alert.labels?.alertname || 'Unknown alert'}
              </p>
              <p className="text-xs text-gray-400 mt-0.5 line-clamp-2">
                {alert.annotations?.summary || alert.annotations?.description || ''}
              </p>
              <p className="text-xs text-gray-600 mt-1">
                {fmtRelative(alert.startsAt)}
              </p>
            </div>
          </div>
        )
      })}
    </div>
  )
}
