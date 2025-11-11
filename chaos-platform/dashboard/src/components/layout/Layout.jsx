import { Outlet, useMatches } from 'react-router-dom'
import Sidebar from './Sidebar'
import Header from './Header'
import { useWebSocket } from '../../hooks/useWebSocket'

const TITLES = {
  '/':           'Dashboard',
  '/chaos':      'Chaos Experiments',
  '/load-tests': 'Load Tests',
  '/results':    'Results',
  '/monitoring': 'Monitoring',
  '/settings':   'Settings',
}

export default function Layout() {
  // Keep WebSocket alive for the entire app lifetime
  useWebSocket()

  const matches = useMatches()
  const currentPath = matches[matches.length - 1]?.pathname ?? '/'
  const title = TITLES[currentPath] || 'Chaos Platform'

  return (
    <div className="flex h-screen overflow-hidden bg-gray-900">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Header title={title} />
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
