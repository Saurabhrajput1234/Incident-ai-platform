import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard,
  Bot,
  FileText,
  CalendarDays,
  Upload,
  Plus,
  Sparkles,
} from 'lucide-react'

export default function Layout() {
  const navigate = useNavigate()

  const navItems = [
    { to: '/dashboard', label: 'Overview', icon: LayoutDashboard },
    { to: '/agents', label: 'Agents', icon: Bot },
    { to: '/incidents', label: 'Incidents', icon: FileText },
    { to: '/shift-roster', label: 'Shift Roster', icon: CalendarDays },
    { to: '/bulk-import', label: 'Bulk Import', icon: Upload },
  ]

  return (
    <div className="flex h-screen w-full overflow-hidden bg-slate-50 text-slate-900 font-sans antialiased">
      {/* Side Navigation Bar */}
      <aside className="w-64 bg-[#0a1124] text-white flex flex-col justify-between shrink-0 h-full border-r border-slate-800/80 p-4 select-none z-20">
        <div>
          {/* Brand Header */}
          <div className="flex items-center gap-3 px-2 py-3 mb-6">
            <div className="w-9 h-9 rounded-xl bg-blue-600/20 border border-blue-500/30 flex items-center justify-center text-blue-400 shadow-sm shadow-blue-500/20 shrink-0">
              <svg className="w-5 h-5 text-blue-500" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
              </svg>
            </div>
            <div>
              <h1 className="font-bold text-[15px] tracking-tight text-white leading-tight">AI Incident</h1>
              <p className="text-xs font-semibold text-slate-400 leading-tight">Management</p>
            </div>
          </div>

          {/* Main Navigation Links */}
          <nav className="space-y-1.5">
            {navItems.map((item) => {
              const Icon = item.icon
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-all duration-150 ${
                      isActive
                        ? 'bg-blue-600 text-white shadow-md shadow-blue-600/30'
                        : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
                    }`
                  }
                >
                  <Icon size={18} className="shrink-0" />
                  <span>{item.label}</span>
                </NavLink>
              )
            })}
          </nav>
        </div>

        {/* Bottom Section */}
        <div className="space-y-3 pt-4 border-t border-slate-800/60">
          {/* Quick Action: New Incident */}
          <button
            onClick={() => navigate('/incidents/new')}
            className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-3 py-2.5 rounded-xl text-xs font-semibold shadow-sm shadow-blue-600/20 transition-all hover:shadow-md"
          >
            <Plus size={15} />
            <span>New Incident</span>
          </button>

          {/* Mockup Badge Card */}
          <div className="p-3.5 rounded-xl bg-slate-900/70 border border-slate-800/90 flex flex-col gap-1.5">
            <div className="flex items-center gap-2.5">
              <Sparkles size={15} className="text-blue-400 shrink-0" />
              <div>
                <p className="text-[11px] font-semibold text-slate-200 leading-tight">Smarter Incidents</p>
                <p className="text-[10px] text-slate-400 leading-tight">Happier Users</p>
              </div>
            </div>
            <p className="text-[10px] text-slate-500 font-mono mt-0.5">v1.0.0</p>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 min-w-0 h-full overflow-y-auto p-6 md:p-8 bg-slate-50">
        <div className="max-w-7xl mx-auto w-full">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
