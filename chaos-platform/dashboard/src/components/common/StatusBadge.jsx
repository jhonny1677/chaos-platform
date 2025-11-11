import { STATUS_COLORS } from '../../utils/constants'
import { clsx } from '../../utils/helpers'

export default function StatusBadge({ status, className }) {
  const colorClass = STATUS_COLORS[status] || STATUS_COLORS.unknown
  return (
    <span className={clsx('inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium', colorClass, className)}>
      {status === 'running' && (
        <span className="mr-1 w-1.5 h-1.5 rounded-full bg-blue-300 animate-pulse" />
      )}
      {status}
    </span>
  )
}
