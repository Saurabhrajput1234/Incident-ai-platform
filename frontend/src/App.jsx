import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import IncidentList from './pages/IncidentList'
import IncidentCreate from './pages/IncidentCreate'
import IncidentDetail from './pages/IncidentDetail'
import ShiftRoster from './pages/ShiftRoster'
import Dashboard from './pages/Dashboard'
import Agents from './pages/Agents'
import BulkImport from './pages/BulkImport'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<Dashboard />} />
        <Route path="agents" element={<Agents />} />
        <Route path="incidents" element={<IncidentList />} />
        <Route path="incidents/new" element={<IncidentCreate />} />
        <Route path="incidents/:id" element={<IncidentDetail />} />
        <Route path="shift-roster" element={<ShiftRoster />} />
        <Route path="bulk-import" element={<BulkImport />} />
      </Route>
    </Routes>
  )
}
