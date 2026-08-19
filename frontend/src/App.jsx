import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import IncidentList from './pages/IncidentList'
import IncidentCreate from './pages/IncidentCreate'
import IncidentDetail from './pages/IncidentDetail'
import ShiftRoster from './pages/ShiftRoster'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Navigate to="/incidents" replace />} />
        <Route path="incidents" element={<IncidentList />} />
        <Route path="incidents/new" element={<IncidentCreate />} />
        <Route path="incidents/:id" element={<IncidentDetail />} />
        <Route path="shift-roster" element={<ShiftRoster />} />
      </Route>
    </Routes>
  )
}
