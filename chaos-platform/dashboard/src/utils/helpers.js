import { clsx } from 'clsx'

export { clsx }

export const downloadJson = (data, filename) => {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export const getStatusColor = (status) => {
  const map = {
    running:   'text-blue-400',
    completed: 'text-green-400',
    failed:    'text-red-400',
    pending:   'text-gray-400',
    stopped:   'text-gray-400',
    aborted:   'text-orange-400',
    passed:    'text-green-400',
    True:      'text-green-400',
    False:     'text-red-400',
  }
  return map[status] || 'text-gray-400'
}

export const isRunning = (status) => status === 'running'
export const isTerminal = (status) => ['completed', 'failed', 'stopped', 'aborted'].includes(status)

// Generate N evenly-spaced time labels ending now
export const makeTimeLabels = (n, intervalSec = 5) =>
  Array.from({ length: n }, (_, i) => {
    const s = (n - 1 - i) * intervalSec
    return s === 0 ? 'now' : `-${s}s`
  })

// Merge two arrays of objects by a key, keeping the latest value
export const mergeById = (existing, incoming, key) => {
  const map = new Map(existing.map((x) => [x[key], x]))
  incoming.forEach((x) => map.set(x[key], x))
  return [...map.values()]
}
