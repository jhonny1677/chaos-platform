import { fmtDate } from '../../utils/formatters'
import { clsx } from '../../utils/helpers'

const EVENT_STYLES = {
  chaos_start:    { dot: 'bg-red-500',   label: 'Chaos Started',   text: 'text-red-400' },
  pod_killed:     { dot: 'bg-red-400',   label: 'Pod Killed',      text: 'text-red-300' },
  chaos_end:      { dot: 'bg-yellow-500', label: 'Chaos Ended',    text: 'text-yellow-400' },
  recovery_start: { dot: 'bg-blue-500',  label: 'Recovery',        text: 'text-blue-400' },
  recovered:      { dot: 'bg-green-500', label: 'Recovered',       text: 'text-green-400' },
  hypothesis_check: { dot: 'bg-purple-500', label: 'Hypothesis',   text: 'text-purple-400' },
}

export default function ChaosTimeline({ events = [] }) {
  if (!events.length) return (
    <p className="text-sm text-gray-500">No timeline events recorded.</p>
  )

  return (
    <ol className="relative border-l border-gray-700 ml-3 space-y-4">
      {events.map((ev, i) => {
        const style = EVENT_STYLES[ev.event_type] || { dot: 'bg-gray-500', label: ev.event_type, text: 'text-gray-400' }
        return (
          <li key={i} className="ml-5">
            <span className={clsx(
              'absolute -left-2 w-4 h-4 rounded-full flex items-center justify-center ring-2 ring-gray-900',
              style.dot
            )} />
            <div className="card py-2 px-3">
              <div className="flex items-center justify-between mb-1">
                <span className={clsx('text-xs font-semibold uppercase tracking-wide', style.text)}>
                  {style.label}
                </span>
                <span className="text-xs text-gray-600">{fmtDate(ev.timestamp)}</span>
              </div>
              {ev.details && (
                <p className="text-xs text-gray-400">
                  {typeof ev.details === 'string' ? ev.details : JSON.stringify(ev.details)}
                </p>
              )}
              {ev.pod_name && <p className="text-xs text-gray-500 font-mono mt-0.5">{ev.pod_name}</p>}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
