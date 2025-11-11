import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Zap, Activity, BarChart2, Eye, Settings, ChevronLeft, ChevronRight } from 'lucide-react'
import { useDispatch, useSelector } from 'react-redux'
import { toggleSidebar, selectSidebarOpen } from '../../store/slices/uiSlice'
import { clsx } from '../../utils/helpers'

const NAV = [
  { to: '/',           label: 'Dashboard',   Icon: LayoutDashboard, end: true },
  { to: '/chaos',      label: 'Chaos',        Icon: Zap },
  { to: '/load-tests', label: 'Load Tests',   Icon: Activity },
  { to: '/results',    label: 'Results',      Icon: BarChart2 },
  { to: '/monitoring', label: 'Monitoring',   Icon: Eye },
  { to: '/settings',   label: 'Settings',     Icon: Settings },
]

export default function Sidebar() {
  const dispatch = useDispatch()
  const open = useSelector(selectSidebarOpen)

  return (
    <aside
      className={clsx(
        'flex flex-col bg-gray-800 border-r border-gray-700 transition-all duration-200 shrink-0',
        open ? 'w-56' : 'w-14'
      )}
    >
      {/* Logo */}
      <div className={clsx('flex items-center gap-2 px-3 py-4 border-b border-gray-700', !open && 'justify-center')}>
        <span className="text-2xl select-none">⚡</span>
        {open && <span className="font-bold text-white text-sm tracking-wide">Chaos Platform</span>}
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-3 space-y-0.5 px-2">
        {NAV.map(({ to, label, Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 px-2 py-2 rounded-lg text-sm font-medium transition-colors duration-150',
                isActive
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-400 hover:text-gray-100 hover:bg-gray-700'
              )
            }
            title={!open ? label : undefined}
          >
            <Icon size={18} className="shrink-0" />
            {open && label}
          </NavLink>
        ))}
      </nav>

      {/* Collapse toggle */}
      <button
        onClick={() => dispatch(toggleSidebar())}
        className="flex items-center justify-center h-10 border-t border-gray-700 text-gray-500 hover:text-gray-200 hover:bg-gray-700 transition-colors"
        aria-label={open ? 'Collapse sidebar' : 'Expand sidebar'}
      >
        {open ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
      </button>
    </aside>
  )
}
