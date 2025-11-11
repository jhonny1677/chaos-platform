import { useState } from 'react'
import { useSelector, useDispatch } from 'react-redux'
import { X } from 'lucide-react'
import { closeModal, selectModals } from '../../store/slices/uiSlice'
import { CHAOS_TYPES, NAMESPACES } from '../../utils/constants'
import { useExperiments } from '../../hooks/useExperiments'

const DEFAULTS = {
  name: '',
  description: '',
  chaos_type: 'pod_kill',
  target_namespace: 'target-app',
  target_label_selector: 'app=target-app',
  parameters: { kill_percentage: 30, duration_seconds: 60 },
  steady_state_thresholds: {
    error_rate_percent: 5,
    latency_p99_ms: 2000,
    min_ready_pods: 1,
  },
}

const PARAMS_FIELDS = {
  pod_kill:       [{ key: 'kill_percentage', label: 'Kill %', type: 'number', min: 1, max: 50 }],
  network_delay:  [
    { key: 'latency_ms',  label: 'Latency (ms)',  type: 'number', min: 0 },
    { key: 'jitter_ms',   label: 'Jitter (ms)',   type: 'number', min: 0 },
    { key: 'duration_seconds', label: 'Duration (s)', type: 'number', min: 1 },
  ],
  cpu_stress:     [
    { key: 'cpu_percentage',   label: 'CPU %',       type: 'number', min: 1, max: 100 },
    { key: 'duration_seconds', label: 'Duration (s)', type: 'number', min: 1 },
  ],
  memory_stress:  [
    { key: 'memory_mb',        label: 'Memory (MB)', type: 'number', min: 1 },
    { key: 'duration_seconds', label: 'Duration (s)', type: 'number', min: 1 },
  ],
}

export default function ExperimentForm() {
  const dispatch = useDispatch()
  const open = useSelector(selectModals).experimentForm
  const { submitExperiment } = useExperiments()
  const [form, setForm] = useState(DEFAULTS)
  const [submitting, setSubmitting] = useState(false)

  if (!open) return null

  const set = (field, val) => setForm((f) => ({ ...f, [field]: val }))
  const setParam = (key, val) => setForm((f) => ({ ...f, parameters: { ...f.parameters, [key]: +val } }))
  const setThreshold = (key, val) => setForm((f) => ({ ...f, steady_state_thresholds: { ...f.steady_state_thresholds, [key]: +val } }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    try { await submitExperiment(form) } finally { setSubmitting(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-gray-800 border border-gray-700 rounded-xl w-full max-w-lg max-h-[90vh] overflow-y-auto shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
          <h2 className="text-base font-semibold text-gray-100">New Chaos Experiment</h2>
          <button onClick={() => dispatch(closeModal('experimentForm'))} className="btn-ghost p-1">
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          {/* Basic info */}
          <div>
            <label className="label">Experiment name *</label>
            <input className="input" value={form.name} onChange={(e) => set('name', e.target.value)} required placeholder="e.g. Pod kill — target app" />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Chaos type</label>
              <select className="select" value={form.chaos_type} onChange={(e) => set('chaos_type', e.target.value)}>
                {Object.entries(CHAOS_TYPES).map(([k, v]) => (
                  <option key={k} value={k}>{v.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Target namespace</label>
              <select className="select" value={form.target_namespace} onChange={(e) => set('target_namespace', e.target.value)}>
                {NAMESPACES.map((ns) => <option key={ns} value={ns}>{ns}</option>)}
              </select>
            </div>
          </div>

          <div>
            <label className="label">Label selector</label>
            <input className="input" value={form.target_label_selector} onChange={(e) => set('target_label_selector', e.target.value)} placeholder="app=my-app" />
          </div>

          {/* Chaos-type-specific parameters */}
          <div>
            <p className="label mb-2">Parameters</p>
            <div className="grid grid-cols-2 gap-3">
              {(PARAMS_FIELDS[form.chaos_type] || []).map(({ key, label, type, min, max }) => (
                <div key={key}>
                  <label className="label text-xs">{label}</label>
                  <input className="input" type={type} min={min} max={max}
                    value={form.parameters[key] ?? ''}
                    onChange={(e) => setParam(key, e.target.value)} />
                </div>
              ))}
            </div>
          </div>

          {/* Steady state thresholds */}
          <div>
            <p className="label mb-2">Steady state thresholds</p>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="label text-xs">Max error %</label>
                <input className="input" type="number" min="0" max="100"
                  value={form.steady_state_thresholds.error_rate_percent}
                  onChange={(e) => setThreshold('error_rate_percent', e.target.value)} />
              </div>
              <div>
                <label className="label text-xs">Max p99 (ms)</label>
                <input className="input" type="number" min="0"
                  value={form.steady_state_thresholds.latency_p99_ms}
                  onChange={(e) => setThreshold('latency_p99_ms', e.target.value)} />
              </div>
              <div>
                <label className="label text-xs">Min ready pods</label>
                <input className="input" type="number" min="0"
                  value={form.steady_state_thresholds.min_ready_pods}
                  onChange={(e) => setThreshold('min_ready_pods', e.target.value)} />
              </div>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button type="button" className="btn-ghost" onClick={() => dispatch(closeModal('experimentForm'))}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={submitting || !form.name}>
              {submitting ? 'Starting…' : 'Run Experiment'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
