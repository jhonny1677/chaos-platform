import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/layout/Layout'
import Dashboard from './pages/Dashboard'
import ChaosExperiments from './pages/ChaosExperiments'
import LoadTests from './pages/LoadTests'
import Results from './pages/Results'
import Monitoring from './pages/Monitoring'
import Settings from './pages/Settings'
import ErrorBoundary from './components/common/ErrorBoundary'

export default function App() {
  return (
    <BrowserRouter>
      <ErrorBoundary>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="chaos" element={<ChaosExperiments />} />
            <Route path="load-tests" element={<LoadTests />} />
            <Route path="results" element={<Results />} />
            <Route path="monitoring" element={<Monitoring />} />
            <Route path="settings" element={<Settings />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </ErrorBoundary>
    </BrowserRouter>
  )
}
