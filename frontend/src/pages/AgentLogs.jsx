import { useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { agentLogApi } from '../api/client'
import Spinner from '../components/Spinner'
import {
  Bot, CheckCircle, XCircle, Clock, Zap, RefreshCw,
  ChevronLeft, ChevronRight, AlertTriangle, Search,
  Filter, X, TrendingUp, Activity,
} from 'lucide-react'

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const AGENT_META = {
  TriageAgent:          { bg: 'bg-purple-100', text: 'text-purple-700', ring: 'ring-purple-300', dot: 'bg-purple-500',  active: 'bg-purple-600 text-white' },
  AcknowledgementAgent: { bg: 'bg-blue-100',   text: 'text-blue-700',   ring: 'ring-blue-300',   dot: 'bg-blue-500',    active: 'bg-blue-600 text-white' },
  PendingAgent:         { bg: 'bg-amber-100',  text: 'text-amber-700',  ring: 'ring-amber-300',  dot: 'bg-amber-500',   active: 'bg-amber-500 text-white' },
  ResolutionAgent:      { bg: 'bg-orange-100', text: 'text-orange-700', ring: 'ring-orange-300', dot: 'bg-orange-500',  active: 'bg-orange-600 text-white' },
}

const STATUS_META = {
  success:   { icon: CheckCircle, bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200', active: 'bg-emerald-600 text-white', label: 'Success' },
  completed: { icon: CheckCircle, bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200', active: 'bg-emerald-600 text-white', label: 'Success' },
  failed:    { icon: XCircle,     bg: 'bg-red-50',     text: 'text-red-700',     border: 'border-red-200',     active: 'bg-red-600 text-white',     label: 'Failed' },
  error:     { icon: XCircle,     bg: 'bg-red-50',     text: 'text-red-700',     border: 'border-red-200',     active: 'bg-red-600 text-white',     label: 'Failed' },
  running:   { icon: RefreshCw,   bg: 'bg-blue-50',    text: 'text-blue-700',    border: 'border-blue-200',    active: 'bg-blue-600 text-white',    label: 'Running' },
}

const AGENT_NAMES = Object.keys(AGENT_META)
const STATUS_OPTIONS = ['success', 'failed', 'running']
const PAGE_SIZE = 50

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function agentMeta(name) {
  return AGENT_META[name] ?? { bg: 'bg-slate-100', text: 'text-slate-600', ring: 'ring-slate-200', dot: 'bg-slate-400', active: 'bg-slate-700 text-white' }
}

function statusMeta(status) {
  return STATUS_META[(status || '').toLowerCase()] ?? {
    icon: Clock, bg: 'bg-slate-50', text: 'text-slate-600', border: 'border-slate-200', active: 'bg-slate-700 text-white', label: status || '—',
  }
}

function formatDuration(secs) {
  if (secs == null) return '—'
  if (secs < 1) return `${Math.round(secs * 1000)}ms`
  if (secs < 60) return `${secs.toFixed(1)}s`
  return `${Math.floor(secs / 60)}m ${Math.round(secs % 60)}s`
}

function formatTs(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

function countActiveFilters(agent, status, incident, dateFrom, dateTo) {
  return [agent, status, incident, dateFrom, dateTo].filter(Boolean).length
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

function KpiCard({ label, value, icon: Icon, iconColor, bg, sub }) {
  return (
    <div className="bg-white rounded-2xl border border-slate-200/90 p-4 shadow-sm hover:shadow-md transition-shadow flex items-center gap-3.5">
      <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${bg}`}>
        <Icon size={18} className={iconColor} />
      </div>
      <div className="min-w-0">
        <p className="text-2xl font-bold tracking-tight text-slate-900 leading-none">{value ?? 0}</p>
        <p className="text-xs font-medium text-slate-500 mt-1 truncate">{label}</p>
        {sub && <p className="text-[11px] text-slate-400 mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}

function AgentBreakdownRow({ agent }) {
  const m = agentMeta(agent.agent_name)
  const rate = agent.total > 0 ? Math.round((agent.success / agent.total) * 100) : 0
  const rateColor = rate >= 90 ? 'bg-emerald-500' : rate >= 70 ? 'bg-amber-400' : 'bg-red-500'
  return (
    <div className="flex items-center gap-4 py-2.5 border-b border-slate-100 last:border-0">
      <span className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full ${m.bg} ${m.text} shrink-0 w-44`}>
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${m.dot}`} />
        <span className="truncate">{agent.agent_name}</span>
      </span>
      <div className="flex items-center gap-3 text-xs flex-1 min-w-0">
        <span className="w-12 text-right font-bold text-slate-800">{agent.total}</span>
        <span className="w-12 text-right font-semibold text-emerald-600">{agent.success}</span>
        <span className="w-10 text-right font-semibold text-red-500">{agent.failed}</span>
        <div className="flex-1 flex items-center gap-2 min-w-[100px]">
          <div className="flex-1 bg-slate-100 rounded-full h-1.5">
            <div className={`h-1.5 rounded-full transition-all ${rateColor}`} style={{ width: `${rate}%` }} />
          </div>
          <span className="w-9 text-right text-slate-500 font-medium">{rate}%</span>
        </div>
        <span className="w-16 text-right text-slate-400 font-mono">{formatDuration(agent.avg_duration_seconds)}</span>
      </div>
    </div>
  )
}

function FilterPill({ label, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all border ${
        active
          ? 'bg-blue-600 text-white border-blue-600 shadow-sm'
          : 'bg-white text-slate-600 border-slate-200 hover:border-slate-300 hover:bg-slate-50'
      }`}
    >
      {label}
    </button>
  )
}

function DetailModal({ log, onClose }) {
  const isFailed = ['failed', 'error'].includes((log.status || '').toLowerCase())
  const isReminder = log.log_type === 'reminder'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-2xl w-full max-w-xl mx-4 overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className={`px-5 py-4 border-b flex items-center justify-between ${isFailed ? 'bg-red-50 border-red-100' : isReminder ? 'bg-amber-50 border-amber-100' : 'bg-slate-50 border-slate-100'}`}>
          <div className="flex items-center gap-2">
            {isFailed
              ? <AlertTriangle size={16} className="text-red-500" />
              : isReminder
                ? <span className="text-base">🔔</span>
                : <CheckCircle size={16} className="text-emerald-500" />
            }
            <span className="text-sm font-bold text-slate-800">
              {isFailed ? 'Execution Error' : isReminder ? 'Reminder Details' : 'Execution Details'}
            </span>
          </div>
          <button onClick={onClose} className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-400 hover:text-slate-600 hover:bg-white/80 transition-colors">
            <X size={15} />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4">
          {/* Full Log ID */}
          <div className="bg-slate-100 rounded-xl px-3 py-2">
            <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Log ID</p>
            <p className="text-xs font-mono font-semibold text-slate-700 mt-0.5 break-all select-all">{log.id}</p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {[
              ['Agent', log.agent_name],
              ['Log Type', log.log_type === 'reminder' ? 'Reminder (Work Note)' : 'Agent Execution'],
              ['Incident', log.incident_number || '—'],
              ['Incident ID', log.incident_id || '—'],
              ['Event', log.triggering_event_type || '—'],
              ['Status', log.status || '—'],
              ['Started At', formatTs(log.started_at)],
              ['Completed At', formatTs(log.completed_at)],
              ['Duration', formatDuration(log.duration_seconds)],
              {/* ['Tries / Attempts', String(log.attempt_count ?? 1)], */}
              ['Correlation ID', log.correlation_id || '—'],
            ].map(([k, v]) => (
              <div key={k} className="bg-slate-50 rounded-xl px-3 py-2">
                <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">{k}</p>
                <p className={`text-xs font-semibold mt-0.5 break-all
                  ${k === 'Incident' ? 'text-blue-600 font-mono' :
                    k === 'Incident ID' || k === 'Correlation ID' ? 'text-slate-500 font-mono text-[10px]' :
                    k === 'Status' && isFailed ? 'text-red-600' :
                    k === 'Status' ? 'text-emerald-600' :
                    'text-slate-800'}`}>
                  {v}
                </p>
              </div>
            ))}
          </div>

          {isFailed && log.error && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-3.5">
              <p className="text-[11px] font-bold text-red-600 uppercase tracking-wider mb-2">Error Details</p>
              <pre className="text-xs text-red-700 whitespace-pre-wrap break-words font-mono leading-relaxed max-h-48 overflow-y-auto">
                {log.error}
              </pre>
            </div>
          )}

          {isReminder && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-3.5">
              <p className="text-[11px] font-bold text-amber-700 uppercase tracking-wider mb-1">Note</p>
              <p className="text-xs text-amber-800">This entry represents an automated reminder sent to the caller by the Pending Agent. Full message is available in the incident work notes.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Page
// ─────────────────────────────────────────────────────────────────────────────

export default function AgentLogs() {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [filterAgent, setFilterAgent] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [filterIncident, setFilterIncident] = useState('')
  const [incidentInput, setIncidentInput] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [selectedLog, setSelectedLog] = useState(null)
  const [showFilters, setShowFilters] = useState(false)

  const activeFilters = countActiveFilters(filterAgent, filterStatus, filterIncident, dateFrom, dateTo)

  const resetFilters = useCallback(() => {
    setFilterAgent('')
    setFilterStatus('')
    setFilterIncident('')
    setIncidentInput('')
    setDateFrom('')
    setDateTo('')
    setPage(1)
  }, [])

  const applyIncidentSearch = () => {
    setFilterIncident(incidentInput.trim())
    setPage(1)
  }

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['agent-log-stats'],
    queryFn: agentLogApi.stats,
    refetchInterval: 30000,
  })

  const { data: logsData, isLoading: logsLoading, isFetching, refetch } = useQuery({
    queryKey: ['agent-logs', page, filterAgent, filterStatus, filterIncident, dateFrom, dateTo],
    queryFn: () => agentLogApi.list({
      page,
      page_size: PAGE_SIZE,
      ...(filterAgent && { agent_name: filterAgent }),
      ...(filterStatus && { status: filterStatus }),
      ...(filterIncident && { incident_number: filterIncident }),
    }),
    refetchInterval: 30000,
    keepPreviousData: true,
  })

  const logs = logsData?.items ?? []
  const total = logsData?.total ?? 0
  const pages = logsData?.pages ?? 1

  const overallRate = stats
    ? Math.round(((stats.total_success ?? 0) / Math.max(stats.total_executions ?? 1, 1)) * 100)
    : 0

  return (
    <div className="space-y-5 pb-10">

      {/* ── Page Header ────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-200/80 pb-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">Agent Execution Logs</h1>
          <p className="text-xs text-slate-500 mt-0.5">Live log of all AI agent runs, outcomes, and performance metrics</p>
        </div>
        <div className="flex items-center gap-2">
          {isFetching && !logsLoading && <Spinner size="sm" />}
          <span className="text-[11px] text-slate-400 font-medium">Auto-refresh 30s</span>
          <button
            onClick={() => refetch()}
            className="flex items-center gap-1.5 text-xs font-semibold text-slate-600 bg-white border border-slate-200 px-3 py-1.5 rounded-xl shadow-sm hover:bg-slate-50 transition-colors"
          >
            <RefreshCw size={13} /> Refresh
          </button>
        </div>
      </div>

      {/* ── Per-Agent Breakdown ─────────────────────────────────────────── */}
      {/* {(stats?.by_agent?.length ?? 0) > 0 && (
        <div className="bg-white border border-slate-200/90 rounded-2xl shadow-sm overflow-hidden">
          <div className="px-5 py-3 bg-slate-50/80 border-b border-slate-100 flex items-center gap-2">
            <Activity size={14} className="text-slate-500" />
            <span className="text-sm font-bold text-slate-800">Agent Performance</span>
          </div>
          <div className="px-5 py-1">
            <div className="flex items-center gap-4 py-2 text-[10px] font-bold text-slate-400 uppercase tracking-widest border-b border-slate-100">
              <span className="w-44 shrink-0">Agent</span>
              <div className="flex items-center gap-3 flex-1 text-right">
                <span className="w-12">Total</span>
                <span className="w-12 text-emerald-500">Success</span>
                <span className="w-10 text-red-400">Failed</span>
                <span className="flex-1 text-left pl-1">Success Rate</span>
                <span className="w-9" />
                <span className="w-16 text-right">Avg Time</span>
              </div>
            </div>
            {stats.by_agent.map(a => <AgentBreakdownRow key={a.agent_name} agent={a} />)}
          </div>
        </div>
      )} */}

      {/* ── Filter Bar + Table ──────────────────────────────────────────── */}
      <div className="bg-white border border-slate-200/90 rounded-2xl shadow-sm overflow-hidden">

        {/* Toolbar */}
        <div className="px-5 py-3.5 bg-slate-50/70 border-b border-slate-100 flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 shrink-0">
            <Bot size={15} className="text-slate-500" />
            <span className="text-sm font-bold text-slate-800">Execution Log</span>
            <span className="text-[11px] font-semibold text-slate-400 bg-white border border-slate-200 px-2 py-0.5 rounded-lg">
              {total.toLocaleString()} records
            </span>
          </div>

          <div className="ml-auto flex items-center gap-2 flex-wrap">
            {/* Incident search */}
            <div className="flex items-center gap-1 border border-slate-200 rounded-lg bg-white overflow-hidden">
              <Search size={13} className="ml-2.5 text-slate-400 shrink-0" />
              <input
                value={incidentInput}
                onChange={e => setIncidentInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && applyIncidentSearch()}
                placeholder="Search incident…"
                className="text-xs px-2 py-1.5 bg-transparent outline-none text-slate-700 placeholder-slate-400 w-36"
              />
              {incidentInput && (
                <button onClick={() => { setIncidentInput(''); setFilterIncident(''); setPage(1) }}
                  className="mr-1.5 text-slate-400 hover:text-slate-600">
                  <X size={11} />
                </button>
              )}
              <button onClick={applyIncidentSearch}
                className="px-2.5 py-1.5 bg-blue-600 text-white text-xs font-semibold hover:bg-blue-700 transition-colors">
                Go
              </button>
            </div>

            {/* Filter toggle */}
            <button
              onClick={() => setShowFilters(v => !v)}
              className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg border transition-colors ${
                showFilters || activeFilters > 0
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
              }`}
            >
              <Filter size={13} />
              Filters
              {activeFilters > 0 && (
                <span className="ml-0.5 bg-white/30 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full leading-none">
                  {activeFilters}
                </span>
              )}
            </button>

            {activeFilters > 0 && (
              <button onClick={resetFilters}
                className="flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-red-500 transition-colors px-2 py-1.5">
                <X size={12} /> Clear all
              </button>
            )}
          </div>
        </div>

        {/* Expanded filter panel */}
        {showFilters && (
          <div className="px-5 py-4 border-b border-slate-100 bg-slate-50/50 space-y-3">
            {/* Agent filter pills */}
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider w-16 shrink-0">Agent</span>
              <FilterPill label="All" active={!filterAgent} onClick={() => { setFilterAgent(''); setPage(1) }} />
              {AGENT_NAMES.map(n => {
                const m = agentMeta(n)
                const isActive = filterAgent === n
                return (
                  <button
                    key={n}
                    onClick={() => { setFilterAgent(isActive ? '' : n); setPage(1) }}
                    className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold border transition-all ${
                      isActive
                        ? `${m.active} border-transparent shadow-sm`
                        : `${m.bg} ${m.text} border-transparent hover:ring-2 ${m.ring}`
                    }`}
                  >
                    <span className={`w-1.5 h-1.5 rounded-full ${isActive ? 'bg-white/70' : m.dot}`} />
                    {n}
                  </button>
                )
              })}
            </div>

            {/* Status filter pills */}
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider w-16 shrink-0">Status</span>
              <FilterPill label="All" active={!filterStatus} onClick={() => { setFilterStatus(''); setPage(1) }} />
              {STATUS_OPTIONS.map(s => {
                const m = statusMeta(s)
                const Icon = m.icon
                const isActive = filterStatus === s
                return (
                  <button
                    key={s}
                    onClick={() => { setFilterStatus(isActive ? '' : s); setPage(1) }}
                    className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold border transition-all ${
                      isActive
                        ? `${m.active} border-transparent shadow-sm`
                        : `${m.bg} ${m.text} ${m.border} hover:shadow-sm`
                    }`}
                  >
                    <Icon size={12} className={isActive ? 'text-white' : ''} />
                    {m.label}
                  </button>
                )
              })}
            </div>
          </div>
        )}

        {/* Active filter chips summary */}
        {activeFilters > 0 && !showFilters && (
          <div className="px-5 py-2.5 border-b border-slate-100 bg-blue-50/40 flex items-center gap-2 flex-wrap text-xs">
            <span className="text-slate-500 font-medium">Filters:</span>
            {filterAgent && (
              <span className="inline-flex items-center gap-1 bg-white border border-slate-200 px-2 py-0.5 rounded-full text-slate-700 font-semibold">
                {filterAgent}
                <button onClick={() => { setFilterAgent(''); setPage(1) }} className="text-slate-400 hover:text-red-500 ml-0.5"><X size={10} /></button>
              </span>
            )}
            {filterStatus && (
              <span className="inline-flex items-center gap-1 bg-white border border-slate-200 px-2 py-0.5 rounded-full text-slate-700 font-semibold capitalize">
                {filterStatus}
                <button onClick={() => { setFilterStatus(''); setPage(1) }} className="text-slate-400 hover:text-red-500 ml-0.5"><X size={10} /></button>
              </span>
            )}
            {filterIncident && (
              <span className="inline-flex items-center gap-1 bg-white border border-slate-200 px-2 py-0.5 rounded-full text-blue-600 font-mono font-semibold">
                {filterIncident}
                <button onClick={() => { setFilterIncident(''); setIncidentInput(''); setPage(1) }} className="text-slate-400 hover:text-red-500 ml-0.5"><X size={10} /></button>
              </span>
            )}
          </div>
        )}

        {/* Table */}
        <div className="overflow-x-auto">
          {logsLoading ? (
            <div className="flex justify-center py-16"><Spinner size="lg" /></div>
          ) : logs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-slate-400 gap-2">
              <Bot size={32} className="opacity-30" />
              <p className="text-sm font-medium">No executions found</p>
              {activeFilters > 0 && (
                <button onClick={resetFilters} className="text-xs text-blue-500 hover:underline mt-1">Clear filters</button>
              )}
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50/80 border-b border-slate-100 text-[11px] font-bold text-slate-400 uppercase tracking-wider text-left">
                  <th className="px-4 py-3 pl-5">Log ID</th>
                  <th className="px-4 py-3">Agent</th>
                  <th className="px-4 py-3">Incident</th>
                  <th className="px-4 py-3">Event</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Started</th>
                  <th className="px-4 py-3">Duration</th>
                  {/* <th className="px-4 py-3 text-center">Tries</th> */}
                  <th className="px-4 py-3 pr-5">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {logs.map((log) => {
                  const am = agentMeta(log.agent_name)
                  const sm = statusMeta(log.status)
                  const StatusIcon = sm.icon
                  const isFailed = ['failed', 'error'].includes((log.status || '').toLowerCase())
                  const isRunning = ['running', 'started'].includes((log.status || '').toLowerCase())
                  return (
                    <tr key={log.id} className={`hover:bg-slate-50/80 transition-colors ${isFailed ? 'bg-red-50/20' : ''}`}>

                      {/* Log ID */}
                      <td className="px-4 py-3 pl-5 whitespace-nowrap">
                        <span className="font-mono text-[11px] text-slate-400 bg-slate-100 px-2 py-0.5 rounded select-all" title={log.id}>
                          {log.id.length > 8 ? `${log.id.slice(0, 8)}…` : log.id}
                        </span>
                      </td>

                      <td className="px-4 py-3 whitespace-nowrap">
                        <span className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full ${am.bg} ${am.text}`}>
                          <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${am.dot}`} />
                          {log.agent_name ?? '—'}
                        </span>
                      </td>

                      <td className="px-4 py-3 whitespace-nowrap">
                        {log.incident_number
                          ? (
                            <button
                              onClick={() => navigate(`/incidents/${log.incident_id}`)}
                              className="font-mono text-xs font-bold text-blue-600 bg-blue-50 px-2 py-0.5 rounded hover:bg-blue-100 hover:text-blue-700 transition-colors underline underline-offset-2"
                            >
                              {log.incident_number}
                            </button>
                          )
                          : <span className="text-slate-300 text-xs">—</span>
                        }
                      </td>

                      <td className="px-4 py-3 whitespace-nowrap max-w-[200px]">
                        {log.log_type === 'reminder' ? (
                          <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded bg-amber-100 text-amber-700 border border-amber-200">
                             {log.triggering_event_type}
                          </span>
                        ) : (
                          <span className="text-[11px] text-slate-500 font-mono bg-slate-100 px-2 py-0.5 rounded truncate block">
                            {(log.triggering_event_type ?? '—').replace('Event', '')}
                          </span>
                        )}
                      </td>

                      <td className="px-4 py-3 whitespace-nowrap">
                        <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full border ${sm.bg} ${sm.text} ${sm.border}`}>
                          <StatusIcon size={12} className={isRunning ? 'animate-spin' : ''} />
                          {sm.label}
                        </span>
                      </td>

                      <td className="px-4 py-3 whitespace-nowrap text-xs text-slate-500 font-medium">
                        {formatTs(log.started_at)}
                      </td>

                      <td className="px-4 py-3 whitespace-nowrap">
                        <span className={`text-xs font-mono font-semibold ${
                          log.duration_seconds == null ? 'text-slate-400' :
                          log.duration_seconds > 30 ? 'text-amber-600' : 'text-slate-700'
                        }`}>
                          {formatDuration(log.duration_seconds)}
                        </span>
                      </td>

                      {/* <td className="px-4 py-3 whitespace-nowrap text-center">
                        <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                          (log.attempt_count ?? 1) > 1
                            ? 'text-amber-700 bg-amber-50'
                            : 'text-slate-400'
                        }`}>
                          {log.attempt_count ?? 1}
                        </span>
                      </td> */}

                      <td className="px-4 py-3 pr-5 whitespace-nowrap">
                        <button
                          onClick={() => setSelectedLog(log)}
                          className={`inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-lg border transition-colors ${
                            isFailed
                              ? 'text-red-600 bg-red-50 border-red-200 hover:bg-red-100'
                              : log.log_type === 'reminder'
                                ? 'text-amber-600 bg-amber-50 border-amber-200 hover:bg-amber-100'
                                : 'text-slate-600 bg-slate-50 border-slate-200 hover:bg-slate-100'
                          }`}
                        >
                          {isFailed ? <><AlertTriangle size={11} /> Error</> : 'View'}
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Pagination */}
        {pages > 1 && (
          <div className="px-5 py-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500 bg-slate-50/50">
            <span className="font-medium">
              {((page - 1) * PAGE_SIZE) + 1}–{Math.min(page * PAGE_SIZE, total)} of <span className="font-bold text-slate-700">{total.toLocaleString()}</span>
            </span>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setPage(1)} disabled={page === 1}
                className="px-2 py-1 rounded border border-slate-200 disabled:opacity-40 hover:bg-white text-[11px] font-semibold transition-colors"
              >
                First
              </button>
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                className="p-1.5 rounded-lg border border-slate-200 disabled:opacity-40 hover:bg-white transition-colors"
              >
                <ChevronLeft size={14} />
              </button>
              <span className="px-3.5 py-1 rounded-lg bg-blue-600 text-white font-bold text-xs shadow-sm">{page}</span>
              <button
                onClick={() => setPage(p => Math.min(pages, p + 1))} disabled={page === pages}
                className="p-1.5 rounded-lg border border-slate-200 disabled:opacity-40 hover:bg-white transition-colors"
              >
                <ChevronRight size={14} />
              </button>
              <button
                onClick={() => setPage(pages)} disabled={page === pages}
                className="px-2 py-1 rounded border border-slate-200 disabled:opacity-40 hover:bg-white text-[11px] font-semibold transition-colors"
              >
                Last
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Error modal */}
      {selectedLog && <DetailModal log={selectedLog} onClose={() => setSelectedLog(null)} />}
    </div>
  )
}
