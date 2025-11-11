import { Loader2 } from 'lucide-react'
import { clsx } from '../../utils/helpers'

export default function LoadingSpinner({ fullscreen = false, size = 32, label = 'Loading…' }) {
  return (
    <div className={clsx('flex flex-col items-center justify-center gap-3', fullscreen && 'h-full')}>
      <Loader2 size={size} className="animate-spin text-blue-400" />
      {label && <span className="text-sm text-gray-500">{label}</span>}
    </div>
  )
}
