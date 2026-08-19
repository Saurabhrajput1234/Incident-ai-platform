import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { AlertCircle, LayoutDashboard, Plus, CalendarDays } from 'lucide-react'

export default function Layout() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen flex flex-col">
      {/* Top Nav */}
      <header className="bg-gray-900 text-white px-6 py-3 flex items-center justify-between shadow-md">
        <div className="flex items-center gap-3">
          <AlertCircle className="text-blue-400" size={22} />
          <span className="font-semibold text-lg tracking-tight">Incident AI Platform</span>
        </div>
        <nav className="flex items-center gap-4 text-sm">
          <NavLink
            to="/incidents"
            className={({ isActive }) =>
              `flex items-center gap-1.5 px-3 py-1.5 rounded transition-colors ${
                isActive ? 'bg-blue-600 text-white' : 'text-gray-300 hover:text-white hover:bg-gray-700'
              }`
            }
          >
            <LayoutDashboard size={15} />
            Incidents
          </NavLink>
          <NavLink
            to="/shift-roster"
            className={({ isActive }) =>
              `flex items-center gap-1.5 px-3 py-1.5 rounded transition-colors ${
                isActive ? 'bg-blue-600 text-white' : 'text-gray-300 hover:text-white hover:bg-gray-700'
              }`
            }
          >
            <CalendarDays size={15} />
            Shift Roster
          </NavLink>
          <button
            onClick={() => navigate('/incidents/new')}
            className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded text-sm font-medium transition-colors"
          >
            <Plus size={15} />
            New Incident
          </button>
        </nav>
      </header>

      {/* Page content */}
      <main className="flex-1 p-6">
        <Outlet />
      </main>
    </div>
  )
}
