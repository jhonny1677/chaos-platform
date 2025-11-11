import { format, formatDistanceToNow, parseISO } from 'date-fns'

export const fmtDate = (iso) => {
  if (!iso) return '—'
  try { return format(parseISO(iso), 'MMM d, HH:mm:ss') } catch { return iso }
}

export const fmtRelative = (iso) => {
  if (!iso) return '—'
  try { return formatDistanceToNow(parseISO(iso), { addSuffix: true }) } catch { return iso }
}

export const fmtDuration = (seconds) => {
  if (!seconds && seconds !== 0) return '—'
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
}

export const fmtMs = (ms) => {
  if (ms === undefined || ms === null) return '—'
  if (ms < 1) return `${(ms * 1000).toFixed(0)}µs`
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

export const fmtRps = (rps) => {
  if (!rps && rps !== 0) return '—'
  return `${rps.toFixed(1)} req/s`
}

export const fmtPct = (pct) => {
  if (pct === undefined || pct === null) return '—'
  return `${pct.toFixed(1)}%`
}

export const fmtCount = (n) => {
  if (n === undefined || n === null) return '—'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

export const truncate = (str, max = 40) =>
  str && str.length > max ? `${str.slice(0, max)}…` : (str || '')
