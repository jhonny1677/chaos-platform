export const STATUS_COLORS = {
  pending:   'bg-gray-600 text-gray-200',
  running:   'bg-blue-600 text-blue-100',
  completed: 'bg-green-700 text-green-100',
  failed:    'bg-red-700 text-red-100',
  stopped:   'bg-gray-600 text-gray-200',
  aborted:   'bg-orange-700 text-orange-100',
  passed:    'bg-green-700 text-green-100',
  unknown:   'bg-gray-700 text-gray-300',
}

export const CHAOS_TYPES = {
  pod_kill:       { label: 'Pod Kill',       color: 'text-red-400',    description: 'Randomly delete pods and measure recovery time' },
  network_delay:  { label: 'Network Delay',  color: 'text-yellow-400', description: 'Inject latency via Chaos Mesh NetworkChaos CRD' },
  cpu_stress:     { label: 'CPU Stress',     color: 'text-orange-400', description: 'Saturate CPU with a stress-ng pod' },
  memory_stress:  { label: 'Memory Stress',  color: 'text-purple-400', description: 'Allocate memory to trigger OOMKill or memory pressure' },
}

export const SCENARIO_TYPES = {
  smoke:  { label: 'Smoke',  color: 'text-blue-400',   description: '10 virtual users for 60 seconds — quick sanity check (fail if error > 1%)' },
  stress: { label: 'Stress', color: 'text-orange-400', description: 'Step ramp 10→200 users until error rate exceeds 20% — finds the breaking point' },
  spike:  { label: 'Spike',  color: 'text-yellow-400', description: 'Normal load → sudden 10× spike → recover. Measures system elasticity' },
  soak:   { label: 'Soak',   color: 'text-purple-400', description: '20 users for 30 minutes — detects memory leaks and latency drift' },
}

export const NAMESPACES = ['target-app', 'monitoring', 'chaos-engine', 'load-tester', 'default']

export const RAMP_STRATEGIES = {
  instant: 'Instant — jump to full load immediately',
  linear:  'Linear — gradually increase over ramp duration',
  step:    'Step — add fixed users every N seconds',
  custom:  'Custom — specify (time, users) waypoints',
}

export const REFRESH_INTERVAL_MS = 5000
export const LIVE_STATS_INTERVAL_MS = 1000
export const ERROR_RATE_THRESHOLD_PCT = 5
