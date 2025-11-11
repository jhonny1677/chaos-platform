import { Bell, RefreshCw, Wifi, WifiOff, Loader2 } from 'lucide-react'
import { useSelector, useDispatch } from 'react-redux'
import { selectWsStatus, selectNotifs, dismissNotification } from '../../store/slices/uiSlice'
import { clsx } from '../../utils/helpers'
import { fmtDate } from '../../utils/formatters'

function WsIndicator({ status }) {
  const map = {
    connected:    { Icon: Wifi,     color: 'text-green-400', label: 'Live' },
    reconnecting: { Icon: Loader2,  color: 'text-yellow-400 animate-spin', label: 'Reconnecting' },
    disconnected: { Icon: WifiOff,  color: 'text-gray-500',  label: 'Offline' },
  }
  const { Icon, color, label } = map[status] || map.disconnected
  return (
    <span className={clsx('flex items-center gap-1 text-xs font-medium', color)}>
      <Icon size={14} />
      {label}
    </span>
  )
}

export default function Header({ title = 'Chaos Platform' }) {
  const dispatch = useDispatch()
  const wsStatus  = useSelector(selectWsStatus)
  const notifs    = useSelector(selectNotifs)
  const unread    = notifs.length

  return (
    <header className="flex items-center justify-between h-14 px-6 bg-gray-800 border-b border-gray-700 shrink-0">
      <h1 className="text-base font-semibold text-gray-100">{title}</h1>

      <div className="flex items-center gap-4">
        <WsIndicator status={wsStatus} />

        <span className="text-xs text-gray-500">{fmtDate(new Date().toISOString())}</span>

        {/* Notification bell */}
        <div className="relative">
          <button
            className="relative text-gray-400 hover:text-gray-200 transition-colors"
            aria-label="Notifications"
          >
            <Bell size={18} />
            {unread > 0 && (
              <span className="absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full w-4 h-4 flex items-center justify-center leading-none">
                {unread > 9 ? '9+' : unread}
              </span>
            )}
          </button>
        </div>
      </div>

      {/* Toast notifications */}
      {notifs.length > 0 && (
        <div className="fixed top-4 right-4 z-50 space-y-2">
          {notifs.map((n) => (
            <div
              key={n.id}
              className={clsx(
                'flex items-start gap-3 px-4 py-3 rounded-lg shadow-lg text-sm max-w-sm border',
                n.type === 'success' && 'bg-green-900 border-green-700 text-green-100',
                n.type === 'error'   && 'bg-red-900 border-red-700 text-red-100',
                n.type === 'info'    && 'bg-blue-900 border-blue-700 text-blue-100',
                !n.type              && 'bg-gray-700 border-gray-600 text-gray-100'
              )}
            >
              <span className="flex-1">{n.message}</span>
              <button
                onClick={() => dispatch(dismissNotification(n.id))}
                className="text-current opacity-60 hover:opacity-100 ml-2 text-lg leading-none"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}
    </header>
  )
}
