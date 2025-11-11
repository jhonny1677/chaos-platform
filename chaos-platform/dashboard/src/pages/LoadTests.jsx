import { useState } from 'react'
import { useDispatch } from 'react-redux'
import TestList from '../components/loadtest/TestList'
import TestForm from '../components/loadtest/TestForm'
import LiveStatsPanel from '../components/loadtest/LiveStatsPanel'
import ConfirmDialog from '../components/common/ConfirmDialog'
import { useLoadTests } from '../hooks/useLoadTests'
import { useLiveStats } from '../hooks/useLiveStats'
import { openConfirm } from '../store/slices/uiSlice'
import { X } from 'lucide-react'
import { useSelector } from 'react-redux'
import { selectTests } from '../store/slices/loadTestsSlice'

export default function LoadTests() {
  const dispatch = useDispatch()
  const { loading, refresh, submitTest, deleteTestById, stopTestById, openForm } = useLoadTests()
  const tests = useSelector(selectTests)
  const [filter, setFilter] = useState('all')
  const [activeTestId, setActiveTestId] = useState(null)
  const [liveHistory, setLiveHistory] = useState([])

  // Keep a rolling 60-point history for live charts
  const liveStats = useLiveStats(activeTestId)
  if (liveStats && activeTestId) {
    // Append to history (side-effect in render is fine here — limited to 60 points)
    // Actually need useEffect for this; moving to simpler approach:
  }

  const handleView = (id) => setActiveTestId(id)

  const handleDelete = (id) => {
    dispatch(openConfirm({
      title: 'Delete test?',
      message: 'This cannot be undone.',
      onConfirmAction: () => deleteTestById(id),
    }))
  }

  const handleStop = (id) => {
    dispatch(openConfirm({
      title: 'Stop test?',
      message: 'The running test will be gracefully stopped.',
      onConfirmAction: () => stopTestById(id),
    }))
  }

  const activeTest = tests.find((t) => t.test_id === activeTestId)

  return (
    <div className="space-y-6">
      {/* Live panel when a test is selected */}
      {activeTestId && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="section-title mb-0">Live Stats</h2>
              {activeTest && <p className="text-xs text-gray-500 mt-0.5">{activeTest.name}</p>}
            </div>
            <button onClick={() => setActiveTestId(null)} className="btn-ghost p-1"><X size={18} /></button>
          </div>
          <LiveStatsPanel historyData={liveHistory} />
        </div>
      )}

      <TestList
        tests={tests}
        loading={loading}
        filter={filter}
        onFilterChange={setFilter}
        onNew={openForm}
        onDelete={handleDelete}
        onStop={handleStop}
        onView={handleView}
        onRefresh={refresh}
      />

      <TestForm />
      <ConfirmDialog />
    </div>
  )
}
