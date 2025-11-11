import { useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { X } from 'lucide-react'
import { closeModal, selectModals } from '../../store/slices/uiSlice'
import { SCENARIO_TYPES, RAMP_STRATEGIES } from '../../utils/constants'
import { useLoadTests } from '../../hooks/useLoadTests'

const TARGET_URL = import.meta.env.VITE_TARGET_URL || 'http://target-app.target-app'

const DEFAULTS = {
  name: '',
  target_url: TARGET_URL,
  scenario_type: 'smoke',
  virtual_users: 10,
  duration_seconds: 60,
  ramp_strategy: 'linear',
  ramp_duration_seconds: 30,
}

export default function TestForm() {
  const dispatch = useDispatch()
  const open = useSelector(selectModals).testForm
  const { submitTest } = useLoadTests()
  const [form, setForm] = useState(DEFAULTS)
  const [submitting, setSubmitting] = useState(false)

  if (!open) return null

  const set = (field, val) => setForm((f) => ({ ...f, [field]: val }))
  const isSmokeOrSoak = form.scenario_type === 'smoke' || form.scenario_type === 'soak'

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    try { await submitTest(form) } finally { setSubmitting(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-gray-800 border border-gray-700 rounded-xl w-full max-w-md shadow-2xl">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
          <h2 className="text-base font-semibold text-gray-100">New Load Test</h2>
          <button onClick={() => dispatch(closeModal('testForm'))} className="btn-ghost p-1">
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="label">Test name *</label>
            <input className="input" value={form.name} onChange={(e) => set('name', e.target.value)} required placeholder="e.g. Smoke — pre-release check" />
          </div>

          <div>
            <label className="label">Target URL</label>
            <input className="input" type="url" value={form.target_url} onChange={(e) => set('target_url', e.target.value)} placeholder="http://..." />
          </div>

          <div>
            <label className="label">Scenario</label>
            <select className="select" value={form.scenario_type} onChange={(e) => set('scenario_type', e.target.value)}>
              {Object.entries(SCENARIO_TYPES).map(([k, v]) => (
                <option key={k} value={k}>{v.label}</option>
              ))}
            </select>
            <p className="text-xs text-gray-500 mt-1">{SCENARIO_TYPES[form.scenario_type]?.description}</p>
          </div>

          {!isSmokeOrSoak && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">Virtual users</label>
                <input className="input" type="number" min="1" max="500"
                  value={form.virtual_users} onChange={(e) => set('virtual_users', +e.target.value)} />
              </div>
              <div>
                <label className="label">Duration (s)</label>
                <input className="input" type="number" min="10"
                  value={form.duration_seconds} onChange={(e) => set('duration_seconds', +e.target.value)} />
              </div>
            </div>
          )}

          {!isSmokeOrSoak && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">Ramp strategy</label>
                <select className="select" value={form.ramp_strategy} onChange={(e) => set('ramp_strategy', e.target.value)}>
                  {Object.keys(RAMP_STRATEGIES).map((k) => (
                    <option key={k} value={k}>{k}</option>
                  ))}
                </select>
              </div>
              {form.ramp_strategy !== 'instant' && (
                <div>
                  <label className="label">Ramp duration (s)</label>
                  <input className="input" type="number" min="0"
                    value={form.ramp_duration_seconds} onChange={(e) => set('ramp_duration_seconds', +e.target.value)} />
                </div>
              )}
            </div>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button type="button" className="btn-ghost" onClick={() => dispatch(closeModal('testForm'))}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={submitting || !form.name}>
              {submitting ? 'Starting…' : 'Start Test'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
