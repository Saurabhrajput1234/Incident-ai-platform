import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { dashboardApi } from '../api/client'
import Spinner from '../components/Spinner'
import { StateBadge, PriorityBadge } from '../components/Badge'
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import {
  AlertCircle, CheckCircle, Clock, Pause, Bot, Users,
  TrendingUp, AlertTriangle, Timer, Zap, Mail, LayoutDashboard,
} from 'lucide-react'

const PRIORITY_COLORS = { Critical: '#ef4444', High: '#f97316', Medium: '#eab308', Low: '#22c55e' }
const STATE_COLORS = ['#3b82f6', '#8b5cf6', '#f59e0b', '#22c55e', '#6b7280', '#ef4444']
const TEMPLATE_COLORS = {
  'Standard Incident': '#22c55e', 'Wrong Request': '#f97316',
  'Access Request': '#3b82f6', 'Service Request': '#8b5cf6', 'Salesforce Request': '#ec4899',
}

const TABS = [
  { id: 'overview', label: 'Overview', icon: <LayoutDashboard size={14} /> },
  { id: 'triage', label: 'Triage Agent', icon: <Bot size={14} /> },
  { id: 'ack', label: 'Acknowledgement Agent', icon: <Mail size={14} /> },
]

function KpiCard({ label, value, icon, bg, sub }) {
  return (
    <div className={`${bg} rounded-lg border border-gray-200 p-4 flex items-center gap-3`}>
      <div className="shrink-0">{icon}</div>
      <div>
        <p className="text-2xl font-bold text-gray-800">{value ?? 0}</p>
        <p className="text-xs text-gray-500">{label}</p>
        {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}

function Card({ title, icon, children }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <div className="px-4 py-2.5 bg-gray-50 border-b border-gray-200 flex items-center gap-2">
        {icon}
        <h3 className="text-sm font-semibold text-gray-700">{title}</h3>
      </div>
      <div className="p-4">{children}</div>
    </div>
  )
}

export default function Dashboard() {
  const [tab, setTab] = useState('overview')

  const { data: stats, isLoading: sl } = useQuery({ queryKey: ['dash-stats'], queryFn: dashboardApi.stats, refetchInterval: 30000 })
  const { data: trends } = useQuery({ queryKey: ['dash-trends'], queryFn: dashboardApi.trends, refetchInterval: 60000 })
  const { data: byPriority } = useQuery({ queryKey: ['dash-priority'], queryFn: dashboardApi.byPriority, refetchInterval: 60000 })
  const { data: byState } = useQuery({ queryKey: ['dash-state'], queryFn: dashboardApi.byState, refetchInterval: 60000 })
  const { data: byGroup } = useQuery({ queryKey: ['dash-group'], queryFn: dashboardApi.byGroup, refetchInterval: 60000, enabled: tab === 'overview' })
  const { data: triageLogs, isLoading: tl } = useQuery({ queryKey: ['dash-triage'], queryFn: dashboardApi.triageLogs, refetchInterval: 30000, enabled: tab === 'triage' })
  const { data: triageStats, isLoading: ts } = useQuery({ queryKey: ['dash-triage-stats'], queryFn: dashboardApi.triageStats, refetchInterval: 30000, enabled: tab === 'triage' })
  const { data: ackStats, isLoading: as_ } = useQuery({ queryKey: ['dash-ack'], queryFn: dashboardApi.ackStats, refetchInterval: 30000, enabled: tab === 'ack' })

  if (sl) return <div className="flex justify-center py-20"><Spinner size="lg" /></div>

  const successRate = triageStats?.total_assignments
    ? Math.round((triageStats.assigned_count / (triageStats.assigned_count + triageStats.failed_count)) * 100)
    : 0

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-800">Analytics Dashboard</h1>
        <span className="text-xs text-gray-400">Auto-refreshes every 30s</span>
      </div>

      {/* Tab Bar */}
      <div className="flex gap-1 bg-gray-100 rounded-lg p-1 w-fit">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              tab === t.id ? 'bg-white text-gray-800 shadow-sm' : 'text-gray-500 hover:text-gray-700'
            }`}>
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* ══ OVERVIEW TAB ══ */}
      {tab === 'overview' && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <KpiCard label="Total Incidents" value={stats?.total} icon={<AlertCircle size={20} className="text-blue-500" />} bg="bg-blue-50" />
            <KpiCard label="Active" value={stats?.active} icon={<TrendingUp size={20} className="text-purple-500" />} bg="bg-purple-50" />
            <KpiCard label="New" value={stats?.new} icon={<Clock size={20} className="text-yellow-500" />} bg="bg-yellow-50" />
            <KpiCard label="On Hold" value={stats?.on_hold} icon={<Pause size={20} className="text-gray-500" />} bg="bg-gray-100" />
            <KpiCard label="Resolved" value={stats?.resolved} icon={<CheckCircle size={20} className="text-green-500" />} bg="bg-green-50" />
            <KpiCard label="Closed" value={stats?.closed} icon={<CheckCircle size={20} className="text-gray-400" />} bg="bg-gray-50" />
            <KpiCard label="Unassigned" value={stats?.unassigned} icon={<Users size={20} className="text-red-500" />} bg="bg-red-50" />
            <KpiCard label="Critical" value={stats?.critical} icon={<AlertTriangle size={20} className="text-red-600" />} bg="bg-red-50" />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card title="Incidents Created (Last 30 Days)" icon={<TrendingUp size={14} className="text-blue-500" />}>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={trends ?? []}>
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={d => d.slice(5)} />
                  <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                  <Tooltip labelFormatter={d => `Date: ${d}`} />
                  <Line type="monotone" dataKey="count" stroke="#3b82f6" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </Card>

            <Card title="Incidents by Priority" icon={<AlertTriangle size={14} className="text-red-500" />}>
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie data={byPriority ?? []} dataKey="count" nameKey="priority" cx="50%" cy="50%" outerRadius={80}
                    label={({ priority, percent }) => `${priority} ${(percent * 100).toFixed(0)}%`}>
                    {(byPriority ?? []).map((entry, i) => (
                      <Cell key={i} fill={PRIORITY_COLORS[entry.priority] ?? '#6b7280'} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </Card>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card title="Incidents by State" icon={<Clock size={14} className="text-gray-500" />}>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={byState ?? []}>
                  <XAxis dataKey="state" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {(byState ?? []).map((_, i) => <Cell key={i} fill={STATE_COLORS[i % STATE_COLORS.length]} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </Card>

            <Card title="Incidents by Assignment Group (Top 15)" icon={<Users size={14} className="text-purple-500" />}>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={byGroup ?? []} layout="vertical" margin={{ left: 0 }}>
                  <XAxis type="number" tick={{ fontSize: 10 }} allowDecimals={false} />
                  <YAxis type="category" dataKey="group" tick={{ fontSize: 9 }} width={140} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#8b5cf6" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Card>
          </div>
        </>
      )}

      {/* ══ TRIAGE AGENT TAB ══ */}
      {tab === 'triage' && (
        <>
          {ts ? <div className="flex justify-center py-10"><Spinner size="lg" /></div> : (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <KpiCard label="Total Assignments" value={triageStats?.total_assignments} icon={<Zap size={20} className="text-purple-500" />} bg="bg-purple-50" />
                <KpiCard label="Success Rate" value={`${successRate}%`} icon={<CheckCircle size={20} className="text-green-500" />} bg="bg-green-50"
                  sub={`${triageStats?.assigned_count ?? 0} assigned / ${triageStats?.failed_count ?? 0} failed`} />
                <KpiCard label="Avg Time to Assign" value={`${triageStats?.avg_time_to_assign_minutes ?? 0}m`}
                  icon={<Timer size={20} className="text-blue-500" />} bg="bg-blue-50" sub="from ticket creation" />
                <KpiCard label="LLM Group Resolved" value={triageStats?.llm_resolved_count} icon={<Bot size={20} className="text-indigo-500" />}
                  bg="bg-indigo-50" sub={`${triageStats?.direct_group_count ?? 0} direct group`} />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <Card title="Assigned vs Failed" icon={<Bot size={14} className="text-purple-500" />}>
                  <ResponsiveContainer width="100%" height={220}>
                    <PieChart>
                      <Pie data={[
                        { name: 'Assigned', value: triageStats?.assigned_count ?? 0 },
                        { name: 'Failed / No Engineer', value: triageStats?.failed_count ?? 0 },
                      ]} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90}
                        label={({ name, percent }) => percent > 0 ? `${name} ${(percent * 100).toFixed(0)}%` : ''}>
                        <Cell fill="#22c55e" />
                        <Cell fill="#ef4444" />
                      </Pie>
                      <Tooltip /><Legend />
                    </PieChart>
                  </ResponsiveContainer>
                </Card>

                <Card title="Assignments by Group (Top 10)" icon={<Bot size={14} className="text-purple-500" />}>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={triageStats?.assignments_by_group ?? []} layout="vertical" margin={{ left: 0 }}>
                      <XAxis type="number" tick={{ fontSize: 10 }} allowDecimals={false} />
                      <YAxis type="category" dataKey="group" tick={{ fontSize: 9 }} width={150} />
                      <Tooltip />
                      <Bar dataKey="count" fill="#8b5cf6" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </Card>
              </div>

              {/* Triage Log Table */}
              <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
                <div className="px-4 py-2.5 bg-gray-50 border-b border-gray-200 flex items-center gap-2">
                  <Bot size={15} className="text-purple-600" />
                  <h3 className="text-sm font-semibold text-gray-700">Assignment Log</h3>
                  <span className="ml-auto text-xs text-gray-400">{triageLogs?.length ?? 0} records</span>
                </div>
                <div className="overflow-x-auto">
                  {tl ? <div className="flex justify-center py-8"><Spinner /></div> : !triageLogs?.length ? (
                    <div className="text-center py-8 text-gray-400 text-sm">No triage activity yet.</div>
                  ) : (
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="bg-gray-50 border-b text-xs text-gray-500 uppercase tracking-wider text-left">
                          <th className="px-4 py-2.5">Incident</th>
                          <th className="px-4 py-2.5">Description</th>
                          <th className="px-4 py-2.5">Group</th>
                          <th className="px-4 py-2.5">Assigned To</th>
                          <th className="px-4 py-2.5">Time to Assign</th>
                          <th className="px-4 py-2.5">State</th>
                          <th className="px-4 py-2.5">Priority</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {triageLogs.map((r, i) => (
                          <tr key={i} className="hover:bg-gray-50">
                            <td className="px-4 py-2.5 font-mono text-blue-600 text-xs font-medium whitespace-nowrap">{r.incident_number}</td>
                            <td className="px-4 py-2.5 text-gray-700 max-w-xs truncate">{r.short_description}</td>
                            <td className="px-4 py-2.5 text-gray-600 text-xs whitespace-nowrap">{r.assignment_group ?? '—'}</td>
                            <td className="px-4 py-2.5 text-xs whitespace-nowrap">
                              {r.assigned_to ?? <span className="text-red-400 italic">unassigned</span>}
                            </td>
                            <td className="px-4 py-2.5 text-xs whitespace-nowrap">
                              {r.minutes_to_assign != null
                                ? <span className={`font-medium ${r.minutes_to_assign < 2 ? 'text-green-600' : r.minutes_to_assign < 10 ? 'text-yellow-600' : 'text-red-600'}`}>
                                    {r.minutes_to_assign}m
                                  </span>
                                : <span className="text-gray-400">—</span>}
                            </td>
                            <td className="px-4 py-2.5"><StateBadge value={r.state} /></td>
                            <td className="px-4 py-2.5"><PriorityBadge value={r.priority} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            </>
          )}
        </>
      )}

      {/* ══ ACKNOWLEDGEMENT AGENT TAB ══ */}
      {tab === 'ack' && (
        <>
          {as_ ? <div className="flex justify-center py-10"><Spinner size="lg" /></div> : (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <KpiCard label="Total Processed" value={ackStats?.total_processed} icon={<Mail size={20} className="text-blue-500" />} bg="bg-blue-50" />
                <KpiCard label="Moved to On Hold" value={ackStats?.on_hold_count} icon={<Pause size={20} className="text-orange-500" />} bg="bg-orange-50" sub="non-standard requests" />
                {(ackStats?.template_breakdown ?? []).filter(t => t.count > 0).slice(0, 2).map(t => (
                  <KpiCard key={t.template} label={t.template} value={t.count}
                    icon={<CheckCircle size={20} style={{ color: t.color }} />} bg="bg-gray-50" />
                ))}
              </div>

              <Card title="Template Usage Breakdown" icon={<Mail size={14} className="text-blue-500" />}>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={ackStats?.template_breakdown ?? []}>
                    <XAxis dataKey="template" tick={{ fontSize: 10 }} />
                    <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                    <Tooltip />
                    <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                      {(ackStats?.template_breakdown ?? []).map((entry, i) => (
                        <Cell key={i} fill={entry.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </Card>

              {/* Ack Log Table */}
              <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
                <div className="px-4 py-2.5 bg-gray-50 border-b border-gray-200 flex items-center gap-2">
                  <Mail size={15} className="text-blue-600" />
                  <h3 className="text-sm font-semibold text-gray-700">Activity Log</h3>
                  <span className="ml-auto text-xs text-gray-400">{ackStats?.recent_logs?.length ?? 0} records</span>
                </div>
                <div className="overflow-x-auto">
                  {!ackStats?.recent_logs?.length ? (
                    <div className="text-center py-8 text-gray-400 text-sm">No acknowledgement activity yet.</div>
                  ) : (
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="bg-gray-50 border-b text-xs text-gray-500 uppercase tracking-wider text-left">
                          <th className="px-4 py-2.5">Incident</th>
                          <th className="px-4 py-2.5">Description</th>
                          <th className="px-4 py-2.5">Template Used</th>
                          <th className="px-4 py-2.5">Group</th>
                          <th className="px-4 py-2.5">Assigned To</th>
                          <th className="px-4 py-2.5">State</th>
                          <th className="px-4 py-2.5">Updated</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {ackStats.recent_logs.map((r, i) => (
                          <tr key={i} className="hover:bg-gray-50">
                            <td className="px-4 py-2.5 font-mono text-blue-600 text-xs font-medium whitespace-nowrap">{r.incident_number}</td>
                            <td className="px-4 py-2.5 text-gray-700 max-w-xs truncate">{r.short_description}</td>
                            <td className="px-4 py-2.5">
                              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border"
                                style={{
                                  color: TEMPLATE_COLORS[r.template] ?? '#6b7280',
                                  borderColor: TEMPLATE_COLORS[r.template] ?? '#6b7280',
                                  backgroundColor: (TEMPLATE_COLORS[r.template] ?? '#6b7280') + '15',
                                }}>
                                {r.template}
                              </span>
                            </td>
                            <td className="px-4 py-2.5 text-gray-600 text-xs whitespace-nowrap">{r.assignment_group ?? '—'}</td>
                            <td className="px-4 py-2.5 text-gray-800 text-xs whitespace-nowrap">{r.assigned_to ?? '—'}</td>
                            <td className="px-4 py-2.5"><StateBadge value={r.state} /></td>
                            <td className="px-4 py-2.5 text-gray-400 text-xs whitespace-nowrap">
                              {r.updated_at ? new Date(r.updated_at).toLocaleString() : '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}
