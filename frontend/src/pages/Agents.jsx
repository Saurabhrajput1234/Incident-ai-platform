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

const PRIORITY_COLORS = { Critical: '#ef4444', High: '#f97316', Medium: '#3b82f6', Low: '#10b981' }
const STATE_COLORS = ['#3b82f6', '#8b5cf6', '#f59e0b', '#10b981', '#64748b', '#ef4444']
const TEMPLATE_COLORS = {
  'Standard Incident': '#10b981', 'Wrong Request': '#f97316',
  'Access Request': '#3b82f6', 'Service Request': '#8b5cf6', 'Salesforce Request': '#ec4899',
}

const TABS = [
  { id: 'overview', label: 'Overview', icon: <LayoutDashboard size={14} /> },
  { id: 'triage', label: 'Triage Agent', icon: <Bot size={14} /> },
  { id: 'ack', label: 'Acknowledgement Agent', icon: <Mail size={14} /> },
]

function KpiCard({ label, value, icon, bg, sub }) {
  return (
    <div className="bg-white rounded-2xl border border-slate-200/90 p-4 shadow-sm hover:shadow-md transition-all flex items-center gap-3.5">
      <div className={`w-10 h-10 rounded-xl ${bg} flex items-center justify-center shrink-0`}>
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-2xl font-bold tracking-tight text-slate-900 leading-none">{value ?? 0}</p>
        <p className="text-xs font-medium text-slate-500 mt-1 truncate">{label}</p>
        {sub && <p className="text-[11px] text-slate-400 mt-0.5 truncate">{sub}</p>}
      </div>
    </div>
  )
}

function Card({ title, icon, children }) {
  return (
    <div className="bg-white border border-slate-200/90 rounded-2xl overflow-hidden shadow-sm hover:shadow-md transition-shadow">
      <div className="px-5 py-3.5 bg-slate-50/70 border-b border-slate-100 flex items-center gap-2.5">
        {icon}
        <h3 className="text-sm font-bold text-slate-800 tracking-tight">{title}</h3>
      </div>
      <div className="p-5">{children}</div>
    </div>
  )
}

export default function Agents() {
  const [tab, setTab] = useState('overview')

  const { data: stats, isLoading: sl } = useQuery({ queryKey: ['dash-stats'], queryFn: dashboardApi.statsagent, refetchInterval: 30000 })
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
    <div className="space-y-6 pb-10">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-200/80 pb-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">Agents Analytics</h1>
          <p className="text-xs text-slate-500 mt-0.5">Performance, assignments and logs for all automated agents</p>
        </div>
        <span className="text-xs font-semibold text-slate-500 bg-white border border-slate-200 px-3 py-1.5 rounded-xl shadow-sm">
          Auto-refreshes every 30s
        </span>
      </div>

      {/* Tab Bar matching executive pills */}
      <div className="flex gap-1.5 bg-slate-200/60 p-1.5 rounded-xl w-fit">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
              tab === t.id
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/40'
            }`}
          >
            {t.icon}
            <span>{t.label}</span>
          </button>
        ))}
      </div>

      {/* ══ OVERVIEW TAB ══ */}
      {tab === 'overview' && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5">
            <KpiCard label="Total Incidents" value={stats?.total} icon={<AlertCircle size={18} className="text-blue-600" />} bg="bg-blue-50" />
            <KpiCard label="Active" value={stats?.active} icon={<TrendingUp size={18} className="text-purple-600" />} bg="bg-purple-50" />
            <KpiCard label="New" value={stats?.new} icon={<Clock size={18} className="text-amber-600" />} bg="bg-amber-50" />
            <KpiCard label="Pending" value={stats?.on_hold} icon={<Pause size={18} className="text-slate-600" />} bg="bg-slate-100" />
            <KpiCard label="Resolved" value={stats?.resolved} icon={<CheckCircle size={18} className="text-emerald-600" />} bg="bg-emerald-50" />
            <KpiCard label="Closed" value={stats?.closed} icon={<CheckCircle size={18} className="text-slate-500" />} bg="bg-slate-50" />
            <KpiCard label="Unassigned" value={stats?.unassigned} icon={<Users size={18} className="text-rose-600" />} bg="bg-rose-50" />
            <KpiCard label="Critical" value={stats?.critical} icon={<AlertTriangle size={18} className="text-red-600" />} bg="bg-red-50" />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <Card title="Incidents Created (Last 30 Days)" icon={<TrendingUp size={16} className="text-blue-500" />}>
              <ResponsiveContainer width="100%" height={210}>
                <LineChart data={trends ?? []}>
                  <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#94a3b8' }} tickFormatter={d => d.slice(5)} />
                  <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#0f172a', borderRadius: '10px', border: 'none', color: '#fff', fontSize: '11px' }}
                    labelFormatter={d => `Date: ${d}`}
                  />
                  <Line type="monotone" dataKey="count" stroke="#2563eb" strokeWidth={2.5} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </Card>

            <Card title="Incidents by Priority" icon={<AlertTriangle size={16} className="text-amber-500" />}>
              <ResponsiveContainer width="100%" height={210}>
                <BarChart data={byPriority ?? []}>
                  <XAxis dataKey="priority" tick={{ fontSize: 11, fill: '#94a3b8' }} />
                  <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} allowDecimals={false} />
                  <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderRadius: '10px', border: 'none', color: '#fff', fontSize: '11px' }} />
                  <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                    {(byPriority ?? []).map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={PRIORITY_COLORS[entry.priority] ?? '#2563eb'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </Card>

            <Card title="Incidents by State" icon={<Clock size={16} className="text-blue-500" />}>
              <ResponsiveContainer width="100%" height={210}>
                <BarChart data={byState ?? []}>
                  <XAxis dataKey="state" tick={{ fontSize: 11, fill: '#94a3b8' }} />
                  <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} allowDecimals={false} />
                  <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderRadius: '10px', border: 'none', color: '#fff', fontSize: '11px' }} />
                  <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                    {(byState ?? []).map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={STATE_COLORS[index % STATE_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </Card>

            <Card title="Incidents by Assignment Group (Top 15)" icon={<Users size={16} className="text-purple-500" />}>
              <ResponsiveContainer width="100%" height={210}>
                <BarChart data={byGroup ?? []} layout="vertical" margin={{ left: 0 }}>
                  <XAxis type="number" tick={{ fontSize: 10, fill: '#94a3b8' }} allowDecimals={false} />
                  <YAxis type="category" dataKey="group" tick={{ fontSize: 9, fill: '#64748b' }} width={140} />
                  <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderRadius: '10px', border: 'none', color: '#fff', fontSize: '11px' }} />
                  <Bar dataKey="count" fill="#8b5cf6" radius={[0, 6, 6, 0]} />
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
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5">
                <KpiCard label="Total Assignments" value={triageStats?.total_assignments} icon={<Zap size={18} className="text-purple-600" />} bg="bg-purple-50" />
                <KpiCard label="Success Rate" value={`${successRate}%`} icon={<CheckCircle size={18} className="text-emerald-600" />} bg="bg-emerald-50"
                  sub={`${triageStats?.assigned_count ?? 0} assigned / ${triageStats?.failed_count ?? 0} failed`} />
                <KpiCard label="Avg Time to Assign" value={`${triageStats?.avg_time_to_assign_minutes ?? 0}m`}
                  icon={<Timer size={18} className="text-blue-600" />} bg="bg-blue-50" sub="from ticket creation" />
                <KpiCard label="LLM Group Resolved" value={triageStats?.llm_resolved_count} icon={<Bot size={18} className="text-indigo-600" />}
                  bg="bg-indigo-50" sub={`${triageStats?.direct_group_count ?? 0} direct group`} />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                <Card title="Assigned vs Failed" icon={<Bot size={16} className="text-purple-500" />}>
                  <ResponsiveContainer width="100%" height={220}>
                    <PieChart>
                      <Pie data={[
                        { name: 'Assigned', value: triageStats?.assigned_count ?? 0 },
                        { name: 'Failed / No Engineer', value: triageStats?.failed_count ?? 0 },
                      ]} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={85}
                        label={({ name, percent }) => percent > 0 ? `${name} ${(percent * 100).toFixed(0)}%` : ''}>
                        <Cell fill="#10b981" />
                        <Cell fill="#ef4444" />
                      </Pie>
                      <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderRadius: '10px', border: 'none', color: '#fff', fontSize: '11px' }} />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                </Card>

                <Card title="Assignments by Group (Top 10)" icon={<Bot size={16} className="text-purple-500" />}>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={triageStats?.assignments_by_group ?? []} layout="vertical" margin={{ left: 0 }}>
                      <XAxis type="number" tick={{ fontSize: 10, fill: '#94a3b8' }} allowDecimals={false} />
                      <YAxis type="category" dataKey="group" tick={{ fontSize: 9, fill: '#64748b' }} width={150} />
                      <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderRadius: '10px', border: 'none', color: '#fff', fontSize: '11px' }} />
                      <Bar dataKey="count" fill="#8b5cf6" radius={[0, 6, 6, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </Card>
              </div>

              {/* Triage Log Table */}
              <div className="bg-white border border-slate-200/90 rounded-2xl overflow-hidden shadow-sm">
                <div className="px-5 py-3.5 bg-slate-50/70 border-b border-slate-100 flex items-center gap-2.5">
                  <Bot size={16} className="text-purple-600" />
                  <h3 className="text-sm font-bold text-slate-800 tracking-tight">Assignment Log</h3>
                  <span className="ml-auto text-xs font-semibold text-slate-400 bg-white border border-slate-200 px-2 py-0.5 rounded-lg">
                    {triageLogs?.length ?? 0} records
                  </span>
                </div>
                <div className="overflow-x-auto">
                  {tl ? <div className="flex justify-center py-10"><Spinner /></div> : !triageLogs?.length ? (
                    <div className="text-center py-10 text-slate-400 text-sm">No triage activity yet.</div>
                  ) : (
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="bg-slate-50/80 border-b border-slate-100 text-xs font-semibold text-slate-500 uppercase tracking-wider text-left">
                          <th className="px-5 py-3">Incident</th>
                          <th className="px-5 py-3">Description</th>
                          <th className="px-5 py-3">Group</th>
                          <th className="px-5 py-3">Assigned To</th>
                          <th className="px-5 py-3">Time to Assign</th>
                          <th className="px-5 py-3">State</th>
                          <th className="px-5 py-3">Priority</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {triageLogs.map((r, i) => (
                          <tr key={i} className="hover:bg-slate-50/80 transition-colors">
                            <td className="px-5 py-3 font-mono text-blue-600 text-xs font-semibold whitespace-nowrap">{r.incident_number}</td>
                            <td className="px-5 py-3 text-slate-700 max-w-xs truncate">{r.short_description}</td>
                            <td className="px-5 py-3 text-slate-600 text-xs whitespace-nowrap">{r.assignment_group ?? '—'}</td>
                            <td className="px-5 py-3 text-xs whitespace-nowrap">
                              {r.assigned_to ?? <span className="text-rose-500 italic font-medium">unassigned</span>}
                            </td>
                            <td className="px-5 py-3 text-xs whitespace-nowrap">
                              {r.minutes_to_assign != null
                                ? <span className={`font-semibold ${r.minutes_to_assign < 2 ? 'text-emerald-600' : r.minutes_to_assign < 10 ? 'text-amber-600' : 'text-rose-600'}`}>
                                    {r.minutes_to_assign}m
                                  </span>
                                : <span className="text-slate-400">—</span>}
                            </td>
                            <td className="px-5 py-3"><StateBadge value={r.state} /></td>
                            <td className="px-5 py-3"><PriorityBadge value={r.priority} /></td>
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
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5">
                <KpiCard label="Total Processed" value={ackStats?.total_processed} icon={<Mail size={18} className="text-blue-600" />} bg="bg-blue-50" />
                <KpiCard label="Moved to Pending" value={ackStats?.on_hold_count} icon={<Pause size={18} className="text-amber-600" />} bg="bg-amber-50" sub="non-standard requests" />
                {(ackStats?.template_breakdown ?? []).filter(t => t.count > 0).slice(0, 2).map(t => (
                  <KpiCard key={t.template} label={t.template} value={t.count}
                    icon={<CheckCircle size={18} style={{ color: t.color }} />} bg="bg-slate-50" />
                ))}
              </div>

              <Card title="Template Usage Breakdown" icon={<Mail size={16} className="text-blue-500" />}>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={ackStats?.template_breakdown ?? []}>
                    <XAxis dataKey="template" tick={{ fontSize: 10, fill: '#94a3b8' }} />
                    <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} allowDecimals={false} />
                    <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderRadius: '10px', border: 'none', color: '#fff', fontSize: '11px' }} />
                    <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                      {(ackStats?.template_breakdown ?? []).map((entry, i) => (
                        <Cell key={i} fill={entry.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </Card>

              {/* Ack Log Table */}
              <div className="bg-white border border-slate-200/90 rounded-2xl overflow-hidden shadow-sm">
                <div className="px-5 py-3.5 bg-slate-50/70 border-b border-slate-100 flex items-center gap-2.5">
                  <Mail size={16} className="text-blue-600" />
                  <h3 className="text-sm font-bold text-slate-800 tracking-tight">Activity Log</h3>
                  <span className="ml-auto text-xs font-semibold text-slate-400 bg-white border border-slate-200 px-2 py-0.5 rounded-lg">
                    {ackStats?.recent_logs?.length ?? 0} records
                  </span>
                </div>
                <div className="overflow-x-auto">
                  {!ackStats?.recent_logs?.length ? (
                    <div className="text-center py-10 text-slate-400 text-sm">No acknowledgement activity yet.</div>
                  ) : (
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="bg-slate-50/80 border-b border-slate-100 text-xs font-semibold text-slate-500 uppercase tracking-wider text-left">
                          <th className="px-5 py-3">Incident</th>
                          <th className="px-5 py-3">Description</th>
                          <th className="px-5 py-3">Template Used</th>
                          <th className="px-5 py-3">Group</th>
                          <th className="px-5 py-3">Assigned To</th>
                          <th className="px-5 py-3">State</th>
                          <th className="px-5 py-3">Updated</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {ackStats.recent_logs.map((r, i) => (
                          <tr key={i} className="hover:bg-slate-50/80 transition-colors">
                            <td className="px-5 py-3 font-mono text-blue-600 text-xs font-semibold whitespace-nowrap">{r.incident_number}</td>
                            <td className="px-5 py-3 text-slate-700 max-w-xs truncate">{r.short_description}</td>
                            <td className="px-5 py-3">
                              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold border"
                                style={{
                                  color: TEMPLATE_COLORS[r.template] ?? '#64748b',
                                  borderColor: TEMPLATE_COLORS[r.template] ?? '#64748b',
                                  backgroundColor: (TEMPLATE_COLORS[r.template] ?? '#64748b') + '15',
                                }}>
                                {r.template}
                              </span>
                            </td>
                            <td className="px-5 py-3 text-slate-600 text-xs whitespace-nowrap">{r.assignment_group ?? '—'}</td>
                            <td className="px-5 py-3 text-slate-800 text-xs whitespace-nowrap">{r.assigned_to ?? '—'}</td>
                            <td className="px-5 py-3"><StateBadge value={r.state} /></td>
                            <td className="px-5 py-3 text-slate-400 text-xs whitespace-nowrap">
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
