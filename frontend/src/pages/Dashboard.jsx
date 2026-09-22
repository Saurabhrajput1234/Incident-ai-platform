import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { dashboardApi } from '../api/client'
import {
  FileText,
  TrendingUp,
  TrendingDown,
  Calendar,
  ChevronDown,
  BarChart2,
  Zap,
  Hourglass,
  Filter,
  Clock,
  CheckCircle2,
  UserCheck,
  Bell,
  RotateCcw,
  MessageSquare,
  Activity,
  ArrowRight,
} from 'lucide-react'
import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  LabelList,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  PieChart,
  Pie,
  Cell,
} from 'recharts'

export default function Dashboard() {
  const [timeRange, setTimeRange] = useState('24h')
  const [group, setGroup] = useState('all')

  const { data: stats, isFetching: statsFetching } = useQuery({
    queryKey: ['dash-stats', timeRange, group],
    queryFn: () =>
      dashboardApi.stats({
        time_range: timeRange,
        assignment_group: group,
      }),
    refetchInterval: 15000,
    retry: false,
  })

  // Sparkline data for Incidents Processed
  const incidentsSparkline = stats?.incidents_processed?.sparkline?.length
    ? stats.incidents_processed.sparkline.map((v) => ({ value: v }))
    : [
        { value: 140 },
        { value: 165 },
        { value: 150 },
        { value: 180 },
        { value: 172 },
        { value: 210 },
        { value: 245 },
      ]

  // Sparkline for AI Automated Actions
  const actionsSparkline = stats?.ai_automated_actions?.sparkline?.length
    ? stats.ai_automated_actions.sparkline.map((v) => ({ value: v }))
    : [
      { value: 95 },
      { value: 110 },
      { value: 105 },
      { value: 128 },
      { value: 122 },
      { value: 145 },
      { value: 168 },
    ]

  // Sparkline for Active Pending Cycles
  const pendingSparkline = stats?.active_pending_cycles?.sparkline?.length
    ? stats.active_pending_cycles.sparkline.map((v) => ({ value: v }))
    : [
      { value: 115 },
      { value: 122 },
      { value: 118 },
      { value: 132 },
      { value: 128 },
      { value: 138 },
      { value: 143 },
    ]

  // Sparkline for Automation Success Rate
  const autoSuccessSparkline = stats?.automation_success?.sparkline?.length
    ? stats.automation_success.sparkline.map((v) => ({ value: v }))
    : [
      { value: 2 },
      { value: 3 },
      { value: 1 },
      { value: 4 },
      { value: 6 },
      { value: 13 },
      { value: 1 },
    ]

  // Sparkline for Human Intervention Rate
  const humanInterventionSparkline = stats?.human_intervention?.sparkline?.length
    ? stats.human_intervention.sparkline.map((v) => ({ value: v }))
    : [
      { value: 2 },
      { value: 2 },
      { value: 1 },
      { value: 3 },
      { value: 4 },
      { value: 8 },
      { value: 0 },
    ]

  // Real Values & Deltas formatting
  const totalIncidents = stats?.incidents_processed?.count != null
    ? stats.incidents_processed.count.toLocaleString()
    : stats?.total != null
      ? stats.total.toLocaleString()
      : '79'

  const automatedActions = stats?.ai_automated_actions?.count != null
    ? stats.ai_automated_actions.count.toLocaleString()
    : '201'

  const autoSuccessRate = stats?.automation_success?.rate || '72.4%'
  const autoSuccessCount = stats?.automation_success?.count != null
    ? stats.automation_success.count.toLocaleString()
    : '21'
  const autoSuccessTotalResolved = stats?.automation_success?.total_resolved != null
    ? stats.automation_success.total_resolved.toLocaleString()
    : '29'
  const autoSuccessDelta = stats?.automation_success?.delta || '+2.1%'

  const humanInterventionRate = stats?.human_intervention?.rate || '10.1%'
  const humanInterventionCount = stats?.human_intervention?.count != null
    ? stats.human_intervention.count.toLocaleString()
    : '8'
  const humanInterventionReplies = stats?.human_intervention?.replies_count != null
    ? stats.human_intervention.replies_count.toLocaleString()
    : '31'
  const humanInterventionDelta = stats?.human_intervention?.delta || '-4.5%'

  const activePendingCycles = stats?.active_pending_cycles?.count != null
    ? stats.active_pending_cycles.count.toLocaleString()
    : stats?.on_hold != null
      ? stats.on_hold.toLocaleString()
      : '48'

  const incidentsDelta = stats?.incidents_processed?.delta || '+12.4%'
  const actionsDelta = stats?.ai_automated_actions?.delta || '+18.2%'
  const pendingDelta = stats?.active_pending_cycles?.delta || '+6.7%'

  // Agent Activity 24h Time-Series data from real work notes
  const agentActivityData = stats?.agent_activity?.length
    ? stats.agent_activity
    : [
      { time: '12 AM', triage: 165, ack: 110, pending: 85, resolution: 32 },
      { time: '2 AM', triage: 140, ack: 95, pending: 70, resolution: 25 },
      { time: '4 AM', triage: 155, ack: 105, pending: 78, resolution: 28 },
      { time: '6 AM', triage: 185, ack: 135, pending: 95, resolution: 42 },
      { time: '8 AM', triage: 215, ack: 165, pending: 120, resolution: 58 },
      { time: '10 AM', triage: 205, ack: 155, pending: 115, resolution: 52 },
      { time: '12 PM', triage: 235, ack: 180, pending: 135, resolution: 72 },
      { time: '2 PM', triage: 220, ack: 170, pending: 125, resolution: 65 },
      { time: '4 PM', triage: 245, ack: 195, pending: 142, resolution: 80 },
      { time: '6 PM', triage: 230, ack: 175, pending: 130, resolution: 75 },
      { time: '8 PM', triage: 210, ack: 160, pending: 118, resolution: 68 },
      { time: '10 PM', triage: 190, ack: 145, pending: 105, resolution: 55 },
    ]

  // Incident Automation Funnel stages from real work notes
  const funnelStages = stats?.funnel?.length
    ? stats.funnel.map((s) => ({
      ...s,
      count: typeof s.count === 'number' ? s.count.toLocaleString() : s.count,
    }))
    : [
      { name: 'Incidents Created', count: '79', percentage: 100, color: 'bg-blue-600' },
      { name: 'Triaged by AI', count: '30', percentage: 38, color: 'bg-sky-500' },
      { name: 'Acknowledged by AI', count: '30', percentage: 38, color: 'bg-emerald-500' },
      { name: 'Pending Workflow', count: '18', percentage: 23, color: 'bg-amber-500' },
      { name: 'User Responses', count: '7', percentage: 9, color: 'bg-purple-500' },
      { name: 'Auto Resolved', count: '29', percentage: 37, color: 'bg-indigo-600' },
    ]

  // Pending Cycle Status Donut data from real work notes
  const pendingCycleData = stats?.pending_cycle_status?.length
    ? stats.pending_cycle_status
    : [
      { name: 'Active', value: 48, percentage: '71%', count: '48', color: '#10b981' },
      { name: 'Completed', value: 18, percentage: '26%', count: '18', color: '#3b82f6' },
      { name: 'Cancelled', value: 2, percentage: '3%', count: '2', color: '#f97316' },
    ]

  const totalPendingCycles = pendingCycleData.reduce(
    (acc, cur) => acc + (typeof cur.value === 'number' ? cur.value : 0),
    0
  )

  // Reminder Distribution Bar Graph data from real work notes or demo specs
  const reminderDistributionData = stats?.reminder_distribution?.length
    ? stats.reminder_distribution
    : [
      { stage: 'Reminder 1', count: 512, color: '#3b82f6' },
      { stage: 'Reminder 2', count: 318, color: '#10b981' },
      { stage: 'Reminder 3', count: 142, color: '#f97316' },
    ]

  const totalReminders = stats?.total_reminders != null
    ? stats.total_reminders
    : reminderDistributionData.reduce((acc, cur) => acc + (cur.count || 0), 0)

  const avgRemindersPerIncident = stats?.avg_reminders_per_incident != null
    ? stats.avg_reminders_per_incident
    : '1.8'

  const userResponseRateR1 = stats?.user_response_rate_r1 || '42%'
  const userResponseRateR2 = stats?.user_response_rate_r2 || '28%'
  const userResponseRateR3 = stats?.user_response_rate_r3 || '18%'

  // Recent Agent Activity (latest 5 tickets)
  const recentActivity = stats?.recent_agent_activity?.length
    ? stats.recent_agent_activity
    : [
        {
          id: '1',
          incident: 'INC0009823',
          agent: 'Resolution',
          action: 'Auto resolved',
          result: 'Success',
          time: '10:24:18',
        },
        {
          id: '2',
          incident: 'INC0009822',
          agent: 'Pending',
          action: 'Reminder 2 sent',
          result: 'Success',
          time: '10:22:11',
        },
        {
          id: '3',
          incident: 'INC0009821',
          agent: 'Acknowledgement',
          action: 'ACK sent (non-standard)',
          result: 'Success',
          time: '10:21:45',
        },
        {
          id: '4',
          incident: 'INC0009820',
          agent: 'Triage',
          action: 'Engineer assigned',
          result: 'Success',
          time: '10:20:03',
        },
        {
          id: '5',
          incident: 'INC0009819',
          agent: 'Resolution',
          action: 'Not resolved (engineer)',
          result: 'Ignored',
        },
      ]

  return (
    <div className="space-y-6 pb-10">
      {/* ── Simple Clean Header ───────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-200/80 pb-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">
            Dashboard
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Overview of AI incident management & operations
          </p>
        </div>

        {/* Filter controls */}
        <div className="flex items-center gap-2.5">
          {statsFetching && (
            <span className="flex items-center gap-1.5 text-[11px] text-blue-600 font-medium px-2 py-1 bg-blue-50 rounded-lg">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-600 animate-pulse" />
              Updating...
            </span>
          )}

          {/* Time range selector */}
          <div className="relative inline-flex items-center">
            <Calendar size={14} className="text-slate-400 absolute left-3 pointer-events-none" />
            <select
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value)}
              className="pl-8 pr-8 py-1.5 bg-white border border-slate-200 rounded-xl text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-colors cursor-pointer appearance-none"
            >
              <option value="24h">Last 24 hours</option>
              <option value="7d">Last 7 days</option>
              <option value="30d">Last 30 days</option>
              <option value="all">All Time</option>
            </select>
            <ChevronDown size={14} className="text-slate-400 absolute right-2.5 pointer-events-none" />
          </div>

          {/* Assignment group filter */}
          <div className="relative inline-flex items-center">
            <select
              value={group}
              onChange={(e) => setGroup(e.target.value)}
              className="pl-3.5 pr-8 py-1.5 bg-white border border-slate-200 rounded-xl text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-colors cursor-pointer appearance-none max-w-[200px] truncate"
            >
              <option value="all">All Assignment Groups</option>
              {stats?.available_groups?.map((g) => (
                <option key={g.name} value={g.name}>
                  {g.name} ({g.count})
                </option>
              ))}
            </select>
            <ChevronDown size={14} className="text-slate-400 absolute right-2.5 pointer-events-none" />
          </div>
        </div>
      </div>

      {/* ── KPI Row: Hero Cards (5-Column Modern Grid) ─────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {/* 1. Incidents Processed Card */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-sm hover:shadow-md transition-shadow relative overflow-hidden flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-500">Incidents Processed</span>
              <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
                <FileText size={16} />
              </div>
            </div>

            <div className="mt-2">
              <span className="text-2xl font-bold tracking-tight text-slate-900">
                {totalIncidents}
              </span>
            </div>
          </div>

          <div className="mt-3 flex items-end justify-between">
            <div className="min-w-0 pr-1">
              <div className="flex items-center gap-1 text-xs font-semibold text-emerald-600">
                <TrendingUp size={14} />
                <span>{incidentsDelta}</span>
                <span className="text-[10px] font-normal text-slate-400">vs prev period</span>
              </div>
              <p className="text-[10px] text-slate-400 mt-0.5 font-medium truncate">
                All incoming tickets
              </p>
            </div>

            {/* Mini Sparkline Chart */}
            <div className="w-14 h-8 shrink-0">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={incidentsSparkline}>
                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke="#2563eb"
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* 2. AI Automated Actions Card */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-sm hover:shadow-md transition-shadow relative overflow-hidden flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-500">AI Automated Actions</span>
              <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
                <Zap size={16} />
              </div>
            </div>

            <div className="mt-2">
              <span className="text-2xl font-bold tracking-tight text-slate-900">
                {automatedActions}
              </span>
            </div>
          </div>

          <div className="mt-3 flex items-end justify-between">
            <div className="min-w-0 pr-1">
              <div className="flex items-center gap-1 text-xs font-semibold text-emerald-600">
                <TrendingUp size={14} />
                <span>{actionsDelta}</span>
                <span className="text-[10px] font-normal text-slate-400">vs prev period</span>
              </div>
              <p className="text-[10px] text-slate-400 mt-0.5 font-medium truncate">
                AI agent executions
              </p>
            </div>

            {/* Mini Sparkline Chart */}
            <div className="w-14 h-8 shrink-0">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={actionsSparkline}>
                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke="#10b981"
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* 3. Automation Success Rate Card */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-sm hover:shadow-md transition-shadow relative overflow-hidden flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-500">Automation Success</span>
              <div className="w-8 h-8 rounded-lg bg-sky-50 text-sky-600 flex items-center justify-center">
                <CheckCircle2 size={16} />
              </div>
            </div>

            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-bold tracking-tight text-slate-900">
                {autoSuccessRate}
              </span>
              <span className="text-[11px] font-medium text-slate-400">
                ({autoSuccessCount} / {autoSuccessTotalResolved})
              </span>
            </div>
          </div>

          <div className="mt-3 flex items-end justify-between">
            <div className="min-w-0 pr-1">
              <div className="flex items-center gap-1 text-xs font-semibold text-emerald-600">
                <TrendingUp size={14} />
                <span>{autoSuccessDelta}</span>
                <span className="text-[10px] font-normal text-slate-400">vs prev period</span>
              </div>
              <p className="text-[10px] text-slate-400 mt-0.5 font-medium truncate" title={`${autoSuccessCount} resolved without human intervention`}>
                Resolved without human edit
              </p>
            </div>

            {/* Mini Sparkline Chart */}
            <div className="w-14 h-8 shrink-0">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={autoSuccessSparkline}>
                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke="#0284c7"
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* 4. Human Intervention Rate Card */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-sm hover:shadow-md transition-shadow relative overflow-hidden flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-500">Human Intervention</span>
              <div className="w-8 h-8 rounded-lg bg-purple-50 text-purple-600 flex items-center justify-center">
                <UserCheck size={16} />
              </div>
            </div>

            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-bold tracking-tight text-slate-900">
                {humanInterventionRate}
              </span>
              <span className="text-[11px] font-medium text-slate-400">
                ({humanInterventionCount} tix)
              </span>
            </div>
          </div>

          <div className="mt-3 flex items-end justify-between">
            <div className="min-w-0 pr-1">
              <div className="flex items-center gap-1 text-xs font-semibold text-emerald-600">
                <TrendingDown size={14} />
                <span>{humanInterventionDelta}</span>
                <span className="text-[10px] font-normal text-slate-400">vs prev period</span>
              </div>
              <p className="text-[10px] text-slate-400 mt-0.5 font-medium truncate" title={`${humanInterventionCount} tickets with engineer work notes (${humanInterventionReplies} notes)`}>
                {humanInterventionReplies} engineer notes
              </p>
            </div>

            {/* Mini Sparkline Chart */}
            <div className="w-14 h-8 shrink-0">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={humanInterventionSparkline}>
                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke="#8b5cf6"
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* 5. Active Pending Cycles Card */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-sm hover:shadow-md transition-shadow relative overflow-hidden flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-500">Active Pending Cycles</span>
              <div className="w-8 h-8 rounded-lg bg-teal-50 text-teal-600 flex items-center justify-center">
                <Hourglass size={16} />
              </div>
            </div>

            <div className="mt-2">
              <span className="text-2xl font-bold tracking-tight text-slate-900">
                {activePendingCycles}
              </span>
            </div>
          </div>

          <div className="mt-3 flex items-end justify-between">
            <div className="min-w-0 pr-1">
              <div className="flex items-center gap-1 text-xs font-semibold text-emerald-600">
                <TrendingUp size={14} />
                <span>{pendingDelta}</span>
                <span className="text-[10px] font-normal text-slate-400">vs prev period</span>
              </div>
              <p className="text-[10px] text-slate-400 mt-0.5 font-medium truncate">
                Pending agent cycles
              </p>
            </div>

            {/* Mini Sparkline Chart */}
            <div className="w-14 h-8 shrink-0">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={pendingSparkline}>
                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke="#0d9488"
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>

      {/* ── Row 2: Analytics Charts (Activity + Funnel) ─────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Agent Activity Line Chart */}
        <div className="lg:col-span-12 xl:col-span-6 bg-white border border-slate-200/90 rounded-2xl p-5 shadow-sm hover:shadow-md transition-shadow">
          {/* Card Header */}
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
                <BarChart2 size={16} />
              </div>
              <div>
                <h3 className="text-sm font-bold text-slate-800 tracking-tight">Agent Activity</h3>
                <p className="text-xs text-slate-400">Number of agent executions over time</p>
              </div>
            </div>

            {/* Time label matching dashboard filter */}
            <div className="flex items-center gap-1 text-xs font-semibold text-slate-600 bg-slate-50 border border-slate-200/80 px-2.5 py-1 rounded-lg">
              <span>
                {timeRange === '7d'
                  ? 'Last 7 days'
                  : timeRange === '30d'
                    ? 'Last 30 days'
                    : timeRange === 'all'
                      ? 'All Time'
                      : 'Last 24 hours'}
              </span>
            </div>
          </div>

          {/* 4-Line Activity Chart */}
          <div className="h-64 w-full mt-4">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={agentActivityData}
                margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                <XAxis
                  dataKey="time"
                  tick={{ fontSize: 11, fill: '#94a3b8' }}
                  axisLine={{ stroke: '#f1f5f9' }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: '#94a3b8' }}
                  axisLine={false}
                  tickLine={false}
                  domain={[0, (dataMax) => Math.max(10, Math.ceil((dataMax * 1.25) / 5) * 5)]}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#0f172a',
                    borderRadius: '10px',
                    border: 'none',
                    color: '#fff',
                    fontSize: '11px',
                    padding: '8px 12px',
                  }}
                  itemStyle={{ padding: '2px 0' }}
                />
                <Line
                  type="monotone"
                  dataKey="triage"
                  name="Triage"
                  stroke="#2563eb"
                  strokeWidth={2.5}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="ack"
                  name="Acknowledgement"
                  stroke="#10b981"
                  strokeWidth={2.5}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="pending"
                  name="Pending"
                  stroke="#f59e0b"
                  strokeWidth={2.5}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="resolution"
                  name="Resolution"
                  stroke="#8b5cf6"
                  strokeWidth={2.5}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Chart Legend */}
          <div className="flex flex-wrap items-center justify-center gap-6 pt-3 mt-1 border-t border-slate-100 text-xs font-medium text-slate-600">
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-blue-600" />
              <span>Triage</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
              <span>Acknowledgement</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-amber-500" />
              <span>Pending</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-purple-500" />
              <span>Resolution</span>
            </div>
          </div>
        </div>

        {/* Incident Automation Funnel */}
        <div className="lg:col-span-12 xl:col-span-6 bg-white border border-slate-200/90 rounded-2xl p-5 shadow-sm hover:shadow-md transition-shadow">
          {/* Card Header */}
          <div className="flex items-center gap-2.5 pb-3 border-b border-slate-100">
            <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
              <Filter size={16} />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-800 tracking-tight">Incident Automation Funnel</h3>
              <p className="text-xs text-slate-400">From incident creation to resolution</p>
            </div>
          </div>

          {/* Funnel Progress Bars */}
          <div className="mt-4 space-y-3.5">
            {funnelStages.map((stage) => (
              <div key={stage.name} className="flex items-center gap-3 text-xs">
                {/* Stage volume count */}
                <span className="w-14 font-semibold text-slate-800 shrink-0 text-right">
                  {stage.count}
                </span>

                {/* Stage title */}
                <span className="w-36 font-medium text-slate-600 shrink-0 truncate">
                  {stage.name}
                </span>

                {/* Horizontal Funnel Bar */}
                <div className="flex-1 bg-slate-100 h-5 rounded-md overflow-hidden p-0.5">
                  <div
                    className={`${stage.color} h-full rounded transition-all duration-500`}
                    style={{ width: `${stage.percentage}%` }}
                  />
                </div>

                {/* Percentage */}
                <span className="w-10 text-right font-semibold text-slate-500 shrink-0">
                  {stage.percentage}%
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Row 3: Pending & Reminder Analytics ──────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Pending Cycle Status Donut Card */}
        <div className="lg:col-span-12 xl:col-span-5 bg-white border border-slate-200/90 rounded-2xl p-5 shadow-sm hover:shadow-md transition-shadow">
          {/* Card Header */}
          <div className="flex items-center gap-2.5 pb-3 border-b border-slate-100">
            <div className="w-8 h-8 rounded-lg bg-rose-50 text-rose-500 flex items-center justify-center">
              <Clock size={16} />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-800 tracking-tight">Pending Cycle Status</h3>
              <p className="text-xs text-slate-400">Current status of pending workflows</p>
            </div>
          </div>

          {/* Donut Chart & Legend */}
          <div className="flex items-center justify-between gap-4 mt-5">
            {/* Donut with center total */}
            <div className="relative w-44 h-44 shrink-0 flex items-center justify-center">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pendingCycleData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={68}
                    strokeWidth={2}
                    stroke="#ffffff"
                    startAngle={90}
                    endAngle={-270}
                  >
                    {pendingCycleData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
              <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                <span className="text-xl font-bold text-slate-900 leading-none">
                  {totalPendingCycles.toLocaleString()}
                </span>
                <span className="text-[11px] font-medium text-slate-400 mt-1">Total Cycles</span>
              </div>
            </div>

            {/* Custom Legend */}
            <div className="flex-1 space-y-3 pr-2">
              {pendingCycleData.map((item) => (
                <div key={item.name} className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <span
                      className="w-2.5 h-2.5 rounded-full shrink-0"
                      style={{ backgroundColor: item.color }}
                    />
                    <span className="font-medium text-slate-600">{item.name}</span>
                  </div>
                  <span className="font-bold text-slate-800">
                    {item.count} <span className="font-normal text-slate-400">({item.percentage})</span>
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Reminder Distribution Card (Exact Match to Demo Picture) */}
        <div className="lg:col-span-12 xl:col-span-7 bg-white border border-slate-200/90 rounded-2xl p-5 shadow-sm hover:shadow-md transition-shadow">
          {/* Card Header matching demo: purple circle with bell */}
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-purple-100 flex items-center justify-center text-purple-600 shrink-0">
              <Bell size={18} />
            </div>
            <div>
              <h3 className="text-base font-bold text-slate-900 tracking-tight">Reminder Distribution</h3>
              <p className="text-xs text-slate-400">Number of reminders sent for active cycles</p>
            </div>
          </div>

          {/* 2-Column Content: Left Bar Chart, Right Metrics Panel */}
          <div className="grid grid-cols-1 md:grid-cols-12 gap-4 mt-5 items-center">
            {/* Left: Bar Chart with Numbers on Top of Bars */}
            <div className="md:col-span-7 h-52 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={reminderDistributionData}
                  margin={{ top: 22, right: 10, left: -22, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                  <XAxis
                    dataKey="stage"
                    tick={{ fontSize: 11, fill: '#64748b', fontWeight: 500 }}
                    axisLine={{ stroke: '#f1f5f9' }}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: '#94a3b8' }}
                    axisLine={false}
                    tickLine={false}
                    allowDecimals={false}
                    domain={[0, (dataMax) => Math.max(20, Math.ceil((dataMax * 1.3) / 10) * 10)]}
                  />
                  <Tooltip
                    cursor={{ fill: '#f8fafc', opacity: 0.8 }}
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const data = payload[0].payload
                        return (
                          <div className="bg-slate-900 text-white px-3 py-2 rounded-xl text-xs shadow-lg border border-slate-800">
                            <div className="font-semibold text-slate-200">{data.stage}</div>
                            <div className="flex items-center gap-2 mt-1">
                              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: data.color }} />
                              <span className="font-bold text-white">{data.count} reminders</span>
                              {data.percentage && <span className="text-slate-400">({data.percentage})</span>}
                            </div>
                          </div>
                        )
                      }
                      return null
                    }}
                  />
                  <Bar
                    dataKey="count"
                    radius={[6, 6, 0, 0]}
                    barSize={48}
                  >
                    <LabelList
                      dataKey="count"
                      position="top"
                      fill="#1e293b"
                      fontSize={12}
                      fontWeight={700}
                      offset={8}
                    />
                    {reminderDistributionData.map((entry, index) => (
                      <Cell key={`reminder-bar-${index}`} fill={entry.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Right: 4-Row Metrics Panel matching demo specs */}
            <div className="md:col-span-5 bg-[#f8faff] border border-blue-100/60 rounded-2xl p-4 flex flex-col justify-center divide-y divide-blue-100/50">
              <div className="flex items-center justify-between py-2.5 first:pt-0">
                <span className="text-xs font-medium text-slate-600">Avg Reminders per Incident</span>
                <span className="text-sm font-bold text-slate-900">{avgRemindersPerIncident}</span>
              </div>
              <div className="flex items-center justify-between py-2.5">
                <span className="text-xs font-medium text-slate-600">User Response Rate (R1)</span>
                <span className="text-sm font-bold text-slate-900">{userResponseRateR1}</span>
              </div>
              <div className="flex items-center justify-between py-2.5">
                <span className="text-xs font-medium text-slate-600">User Response Rate (R2)</span>
                <span className="text-sm font-bold text-slate-900">{userResponseRateR2}</span>
              </div>
              <div className="flex items-center justify-between py-2.5 last:pb-0">
                <span className="text-xs font-medium text-slate-600">User Response Rate (R3)</span>
                <span className="text-sm font-bold text-slate-900">{userResponseRateR3}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Row 4: Recent Agent Activity (Latest 5 Tickets) ─────────────────── */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-sm hover:shadow-md transition-shadow">
        {/* Card Header matching demo picture */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-100/80">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-sky-100 flex items-center justify-center text-sky-600 shrink-0">
              <Activity size={18} />
            </div>
            <div>
              <h3 className="text-base font-bold text-slate-900 tracking-tight">Recent Agent Activity</h3>
              <p className="text-xs text-slate-400">Latest agent executions across all incidents</p>
            </div>
          </div>
          <Link
            to="/incidents"
            className="text-xs font-semibold text-blue-600 hover:text-blue-700 flex items-center gap-1.5 px-3 py-1.5 rounded-lg hover:bg-blue-50/60 transition-colors group"
          >
            <span>View All</span>
            <ArrowRight size={13} className="transition-transform group-hover:translate-x-0.5" />
          </Link>
        </div>

        {/* Responsive Table */}
        <div className="overflow-x-auto mt-2">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-100 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                <th className="py-3 px-4 font-semibold">Time</th>
                <th className="py-3 px-4 font-semibold">Incident</th>
                <th className="py-3 px-4 font-semibold">Agent</th>
                <th className="py-3 px-4 font-semibold">Action</th>
                <th className="py-3 px-4 font-semibold text-right">Result</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100/80">
              {recentActivity.map((row, idx) => (
                <tr
                  key={row.id || idx}
                  className="hover:bg-slate-50/80 transition-colors group"
                >
                  {/* Time */}
                  <td className="py-3.5 px-4 text-xs text-slate-500 font-mono whitespace-nowrap">
                    {row.time}
                  </td>

                  {/* Incident link */}
                  <td className="py-3.5 px-4 whitespace-nowrap">
                    <Link
                      to={row.id && row.id.length > 5 ? `/incidents/${row.id}` : '/incidents'}
                      className="text-xs font-semibold text-blue-600 hover:text-blue-800 hover:underline inline-flex items-center gap-1"
                      title={row.short_description || row.incident}
                    >
                      {row.incident}
                    </Link>
                  </td>

                  {/* Agent */}
                  <td className="py-3.5 px-4 whitespace-nowrap">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                      row.agent === 'Resolution'
                        ? 'bg-purple-50 text-purple-700 border border-purple-200/50'
                        : row.agent === 'Pending'
                          ? 'bg-amber-50 text-amber-700 border border-amber-200/50'
                          : row.agent === 'Acknowledgement'
                            ? 'bg-indigo-50 text-indigo-700 border border-indigo-200/50'
                            : 'bg-sky-50 text-sky-700 border border-sky-200/50'
                    }`}>
                      {row.agent}
                    </span>
                  </td>

                  {/* Action */}
                  <td className="py-3.5 px-4 text-xs text-slate-600">
                    <span className="truncate block max-w-xs md:max-w-md" title={row.action}>
                      {row.action}
                    </span>
                  </td>

                  {/* Result Badge */}
                  <td className="py-3.5 px-4 text-xs whitespace-nowrap text-right">
                    {row.result === 'Success' ? (
                      <span className="inline-flex items-center gap-1.5 font-semibold text-emerald-600">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0" />
                        Success
                      </span>
                    ) : row.result === 'Ignored' ? (
                      <span className="inline-flex items-center gap-1.5 font-semibold text-amber-500">
                        <span className="w-0 h-0 border-l-[3.5px] border-l-transparent border-r-[3.5px] border-r-transparent border-b-[6px] border-b-amber-500 shrink-0" />
                        Ignored
                      </span>
                    ) : row.result === 'Failed' ? (
                      <span className="inline-flex items-center gap-1.5 font-semibold text-rose-500">
                        <span className="w-1.5 h-1.5 rounded-full bg-rose-500 shrink-0" />
                        Failed
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 font-semibold text-blue-500">
                        <span className="w-1.5 h-1.5 rounded-full bg-blue-500 shrink-0" />
                        {row.result || 'Pending'}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
