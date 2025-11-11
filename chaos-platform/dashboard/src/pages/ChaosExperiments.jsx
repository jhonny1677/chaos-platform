import { useState } from 'react'
import { useSelector, useDispatch } from 'react-redux'
import ExperimentList from '../components/chaos/ExperimentList'
import ExperimentForm from '../components/chaos/ExperimentForm'
import ChaosTimeline from '../components/chaos/ChaosTimeline'
import HypothesisResult from '../components/chaos/HypothesisResult'
import ConfirmDialog from '../components/common/ConfirmDialog'
import { useExperiments } from '../hooks/useExperiments'
import { selectFilteredExperiments, selectExperimentsLoading, selectExperimentResult } from '../store/slices/experimentsSlice'
import { openConfirm } from '../store/slices/uiSlice'
import { X } from 'lucide-react'
import { CHAOS_TYPES } from '../utils/constants'

export default function ChaosExperiments() {
  const dispatch = useDispatch()
  const { experiments: _, loading, refresh, deleteExp, loadResult, openForm, applyFilters } = useExperiments()
  const experiments = useSelector(selectFilteredExperiments)
  const [filters, setFilters] = useState({ status: 'all', type: 'all' })
  const [detailId, setDetailId] = useState(null)

  const detailExp    = experiments.find((e) => e.experiment_id === detailId)
  const detailResult = useSelector(selectExperimentResult(detailId))

  const handleView = (id) => {
    setDetailId(id)
    loadResult(id)
  }

  const handleDelete = (id) => {
    dispatch(openConfirm({
      title: 'Delete experiment?',
      message: 'This action cannot be undone.',
      onConfirmAction: () => deleteExp(id),
    }))
  }

  const handleFilterChange = (change) => {
    const next = { ...filters, ...change }
    setFilters(next)
    applyFilters(next)
  }

  return (
    <div className="space-y-6">
      <ExperimentList
        experiments={experiments}
        loading={loading}
        filters={filters}
        onFilterChange={handleFilterChange}
        onNew={openForm}
        onDelete={handleDelete}
        onView={handleView}
        onRefresh={refresh}
      />

      {/* Detail drawer */}
      {detailId && detailExp && (
        <div className="fixed inset-0 z-40 flex">
          <div className="flex-1 bg-black/50" onClick={() => setDetailId(null)} />
          <div className="w-full max-w-lg bg-gray-800 border-l border-gray-700 overflow-y-auto p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-base font-semibold text-gray-100">{detailExp.name}</h2>
                <p className="text-xs text-gray-500 mt-0.5">
                  {CHAOS_TYPES[detailExp.chaos_type]?.label} · {detailExp.target_namespace}
                </p>
              </div>
              <button onClick={() => setDetailId(null)} className="btn-ghost p-1"><X size={18} /></button>
            </div>

            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-semibold text-gray-200 mb-3">Hypothesis Result</h3>
                <HypothesisResult result={detailResult} />
              </div>

              <div>
                <h3 className="text-sm font-semibold text-gray-200 mb-3">Event Timeline</h3>
                <ChaosTimeline events={detailResult?.timeline ?? detailExp.result_summary?.timeline ?? []} />
              </div>
            </div>
          </div>
        </div>
      )}

      <ExperimentForm />
      <ConfirmDialog />
    </div>
  )
}
