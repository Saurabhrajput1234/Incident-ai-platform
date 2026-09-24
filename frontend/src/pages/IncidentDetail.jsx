import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { incidentApi, triageApi, workNoteApi, pendingApi } from '../api/client'
import { PriorityBadge, StateBadge } from '../components/Badge'
import Spinner from '../components/Spinner'
import { ArrowLeft, Bot, RefreshCw, User, Clock, Tag, Server, Pencil, X, CheckCircle, MessageSquare, Plus } from 'lucide-react'
import { useState, useEffect, useRef } from 'react'
import { useForm } from 'react-hook-form'

export default function IncidentDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [triageResult, setTriageResult] = useState(null)
  const [editOpen, setEditOpen] = useState(false)
  const [triagePopup, setTriagePopup] = useState(null)
  const [addNoteOpen, setAddNoteOpen] = useState(false)
  const [newNoteText, setNewNoteText] = useState('')
  const [noteSourceType, setNoteSourceType] = useState('USER')
  const [noteSourceName, setNoteSourceName] = useState('')
  const [addingNote, setAddingNote] = useState(false)
  const prevAssignedTo = useRef('__initial__') // sentinel: skip the very first load
  const reloadedRef = useRef(false)

  // Poll while incident is new/in_progress with no assigned_to
  const { data: incident, isLoading } = useQuery({
    queryKey: ['incident', id],
    queryFn: () => incidentApi.get(id),
    refetchInterval: (query) => {
      const inc = query.state.data
      if (!inc) return false
      const shouldPoll = (inc.state === 'new' || inc.state === 'in_progress') && !inc.assigned_to
      return shouldPoll ? 3000 : false
    },
  })

  // Work notes — refresh every 5s while the incident is active
  const { data: workNotes = [] } = useQuery({
    queryKey: ['work-notes', id],
    queryFn: () => workNoteApi.list(id),
    refetchInterval: 5000,
    enabled: !!id,
  })

  // Pending cycle status — poll every 5s
  const { data: cycleData } = useQuery({
    queryKey: ['pending-cycle', id],
    queryFn: () => pendingApi.getCycle(id),
    refetchInterval: 5000,
    enabled: !!id,
  })
  const activeCycle = cycleData?.cycle?.status === 'ACTIVE' ? cycleData.cycle : null

  // Auto-fill source name when source type changes
  useEffect(() => {
    if (!incident) return
    if (noteSourceType === 'USER') {
      setNoteSourceName(incident.caller || '')
    } else if (noteSourceType === 'ENGINEER') {
      setNoteSourceName(incident.assigned_to || '')
    }
  }, [noteSourceType, incident])

  // Only show popup when assigned_to transitions null → value AFTER initial load
  useEffect(() => {
    if (!incident) return
    const prev = prevAssignedTo.current
    const curr = incident.assigned_to ?? null

    if (prev === '__initial__') {
      // First load — just record the current value, never show popup
      prevAssignedTo.current = curr
      return
    }

    if (!prev && curr && !reloadedRef.current) {
      // Transitioned from empty to assigned during this session
      reloadedRef.current = true
      setTriagePopup({ assignedTo: curr, assignmentGroup: incident.assignment_group })
      qc.invalidateQueries(['incidents'])
      setTimeout(() => {
        setTriagePopup(null)
        qc.invalidateQueries(['incident', id])
      }, 2500)
    }

    prevAssignedTo.current = curr
  }, [incident?.assigned_to])

  const [agentPopup, setAgentPopup] = useState(null)
  const [toasts, setToasts] = useState([])

  const showAgentPopup = (note) => {
    const agentConfig = {
      'TRIAGE_AGENT':          { title: 'Triage Agent',           action: 'Engineer assigned to incident' },
      'ACKNOWLEDGEMENT_AGENT': { title: 'Acknowledgement Agent',  action: 'Acknowledgement email sent to user' },
      'PENDING_AGENT':         { title: 'Pending Agent',          action: 'Reminder cycle updated' },
      'RESOLUTION_AGENT':      { title: 'Resolution Agent',       action: 'User response processed' },
      'ENGINEER':              { title: 'Engineer',               action: 'Work note added' },
      'SYSTEM':                { title: 'System',                 action: 'System event recorded' },
      'USER':                  { title: 'User',                   action: 'User responded' },
    }
    const config = agentConfig[note.source_type] ?? agentConfig['SYSTEM']
    const toastId = Date.now()

    // Prepend so newest is always on top
    setToasts(prev => [{ id: toastId, title: config.title, action: config.action, message: note.message }, ...prev])

    // Auto-remove after 8 seconds
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== toastId))
    }, 5000)
  }

  // WebSocket connection for real-time work note updates — CONNECT IMMEDIATELY
  useEffect(() => {
    if (!id) return

    const ws = new WebSocket(`ws://localhost:3000/ws/incidents/${id}`)

    ws.onopen = () => {
      console.log('[WebSocket] Connected to incident', id)
      // Force refresh work notes once connected
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ['work-notes', id] })
      }, 100)
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'WORK_NOTE_ADDED') {
          showAgentPopup(data.work_note)
          qc.invalidateQueries({ queryKey: ['work-notes', id] })
          qc.invalidateQueries({ queryKey: ['incident', id] })
        }
      } catch (e) {
        console.error('[WebSocket] Parse error:', e)
      }
    }

    ws.onerror = (error) => {
      console.error('[WebSocket] Error:', error)
    }

    ws.onclose = () => {
      console.log('[WebSocket] Disconnected')
    }

    return () => {
      ws.close()
    }
  }, [id])

  const triageMut = useMutation({
    mutationFn: () => triageApi.run(id),
    onSuccess: (res) => {
      setTriageResult(res)
      qc.invalidateQueries(['incident', id])
      qc.invalidateQueries(['incidents'])
      qc.invalidateQueries(['work-notes', id])
    },
    onMutate: () => {
      // Reset sentinels so popup fires if triage assigns a new engineer
      prevAssignedTo.current = null
      reloadedRef.current = false
    },
  })

  const updateMut = useMutation({
    mutationFn: (data) => incidentApi.update(id, data),
    onSuccess: async () => {
      setEditOpen(false)
      // Immediately refetch so UI reflects saved state
      await qc.refetchQueries({ queryKey: ['incident', id] })
      qc.invalidateQueries(['incidents'])
      qc.invalidateQueries(['work-notes', id])
      qc.invalidateQueries(['pending-cycle', id])
    },
  })

  const handleAddNote = async () => {
    const msg = newNoteText.trim()
    const name = noteSourceName.trim()
    if (!msg || !name) return
    setAddingNote(true)
    try {
      await workNoteApi.add(id, {
        message: msg,
        source_type: noteSourceType,
        source_name: name,
      })
      setNewNoteText('')
      setNoteSourceName('')
      setNoteSourceType('USER')
      setAddNoteOpen(false)
      qc.invalidateQueries(['work-notes', id])
      qc.invalidateQueries(['pending-cycle', id])
    } finally {
      setAddingNote(false)
    }
  }

  if (isLoading) {
    return <div className="flex justify-center py-20"><Spinner size="lg" /></div>
  }

  if (!incident) {
    return <div className="text-center py-20 text-gray-400">Incident not found.</div>
  }

  const canTriage = incident.state === 'new' || incident.state === 'in_progress'

  return (
    <div className="max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-5 flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/incidents')}
            className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded transition-colors"
          >
            <ArrowLeft size={18} />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-lg font-bold text-blue-600">{incident.incident_number}</span>
              <StateBadge value={incident.state} />
              <PriorityBadge value={incident.priority} />
            </div>
            <p className="text-gray-700 mt-0.5">{incident.short_description}</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setEditOpen(true)}
            className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 text-sm font-medium rounded transition-colors"
          >
            <Pencil size={14} /> Edit
          </button>
          <button
            onClick={() => triageMut.mutate()}
            disabled={triageMut.isPending || !canTriage}
            title={!canTriage ? 'Triage only runs for new or active incidents' : 'Re-run triage to reassign engineer'}
            className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white text-sm font-medium rounded transition-colors"
          >
            {triageMut.isPending ? <Spinner size="sm" /> : <Bot size={15} />}
            {triageMut.isPending ? 'Running Triage…' : 'Run Triage Agent'}
          </button>
        </div>
      </div>

      {/* Triage result banner */}
      {triageResult && (
        <div className={`rounded-lg border px-4 py-3 mb-5 text-sm ${triageResult.success ? 'bg-green-50 border-green-200 text-green-800' : 'bg-red-50 border-red-200 text-red-700'}`}>
          <p className="font-medium flex items-center gap-1.5">
            <Bot size={15} />
            {triageResult.success ? 'Triage Agent completed' : 'Triage failed'}
          </p>
          {triageResult.reasoning && <p className="mt-1">{triageResult.reasoning}</p>}
          {triageResult.errors?.length > 0 && (
            <ul className="mt-1 list-disc list-inside">{triageResult.errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
          )}
        </div>
      )}

      {triageMut.isError && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded px-4 py-3 text-sm mb-5">
          {triageMut.error?.response?.data?.detail ?? triageMut.error?.message}
        </div>
      )}

      <div className="grid grid-cols-3 gap-4">
        {/* Main col */}
        <div className="col-span-2 space-y-4">
          <Card title="Description">
            <p className="text-sm text-gray-700 whitespace-pre-wrap">
              {incident.description ?? <span className="text-gray-400 italic">No description provided.</span>}
            </p>
          </Card>

          <Card title={
            <div className="flex items-center justify-between">
              <span>Work Notes {workNotes.length > 0 && <span className="text-xs font-normal text-gray-400 ml-1">({workNotes.length})</span>}</span>
              <button
                onClick={() => setAddNoteOpen(v => !v)}
                className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700 font-medium"
              >
                <Plus size={13} /> Add Note
              </button>
            </div>
          }>
            {/* Add note form */}
            {addNoteOpen && (
              <div className="mb-4 p-3 bg-gray-50 border border-gray-200 rounded-lg space-y-3">
                {/* Source type + name row */}
                <div className="flex gap-2">
                  <div className="flex-shrink-0">
                    <label className="block text-xs font-medium text-gray-500 mb-1">Source</label>
                    <select
                      value={noteSourceType}
                      onChange={e => setNoteSourceType(e.target.value)}
                      className="border border-gray-300 rounded px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                    >
                      <option value="USER">User</option>
                      <option value="ENGINEER">Engineer</option>
                    </select>
                  </div>
                  <div className="flex-1">
                    <label className="block text-xs font-medium text-gray-500 mb-1">
                      {noteSourceType === 'ENGINEER' ? 'Engineer Name' : 'Your Name'}
                    </label>
                    <input
                      value={noteSourceName}
                      onChange={e => setNoteSourceName(e.target.value)}
                      placeholder={noteSourceType === 'ENGINEER' ? 'e.g. Priya Sharma' : 'e.g. Rahul Sharma'}
                      className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                </div>

                {/* Message */}
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">Note</label>
                  <textarea
                    value={newNoteText}
                    onChange={e => setNewNoteText(e.target.value)}
                    rows={3}
                    placeholder="Write a work note…"
                    className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                  />
                </div>

                <div className="flex gap-2">
                  <button
                    onClick={handleAddNote}
                    disabled={addingNote || !newNoteText.trim() || !noteSourceName.trim()}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs font-medium rounded"
                  >
                    {addingNote ? <Spinner size="sm" /> : <MessageSquare size={12} />}
                    {addingNote ? 'Adding…' : 'Add Note'}
                  </button>
                  <button
                    onClick={() => { setAddNoteOpen(false); setNewNoteText(''); setNoteSourceName(''); setNoteSourceType('USER') }}
                    className="px-3 py-1.5 text-xs text-gray-600 border border-gray-300 rounded hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {/* Work notes timeline */}
            {workNotes.length === 0 ? (
              <p className="text-sm text-gray-400 italic">No work notes.</p>
            ) : (
              <div className="space-y-3">
                {workNotes.map((note) => (
                  <div key={note.id} className="border border-gray-200 rounded-lg p-4 bg-white hover:shadow-md transition-shadow">
                    <WorkNoteEntry note={note} />
                  </div>
                ))}
              </div>
            )}
          </Card>

          {incident.comments && (
            <Card title="Comments">
              <p className="text-sm text-gray-700 whitespace-pre-wrap">{incident.comments}</p>
            </Card>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          <Card title="Classification">
            <dl className="space-y-2 text-sm">
              <Row icon={<Tag size={13} />} label="Priority"><PriorityBadge value={incident.priority} /></Row>
              <Row icon={<RefreshCw size={13} />} label="State"><StateBadge value={incident.state} /></Row>
              {activeCycle && (
                <Row icon={<Clock size={13} />} label="Pending Cycle">
                  <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200">
                    Reminder {activeCycle.reminder_count}/{activeCycle.max_reminders} Active
                  </span>
                </Row>
              )}
              <Row label="Category">{incident.category ?? '—'}</Row>
              <Row label="Subcategory">{incident.subcategory ?? '—'}</Row>
              <Row label="Impact">{mapImpact(incident.impact)}</Row>
              <Row label="Urgency">{mapUrgency(incident.urgency)}</Row>
              <Row label="Environment">{incident.environment ?? '—'}</Row>
              <Row label="Source">{incident.source}</Row>
            </dl>
          </Card>

          <Card title="Assignment">
            <dl className="space-y-2 text-sm">
              <Row icon={<User size={13} />} label="Group">
                {incident.assignment_group ?? <span className="text-gray-400 italic">unassigned</span>}
              </Row>
              <Row label="Assigned To">
                {incident.assigned_to ?? <span className="text-gray-400 italic">empty</span>}
              </Row>
              <Row label="Caller">{incident.caller ?? '—'}</Row>
            </dl>
          </Card>

          <Card title="CMDB">
            <dl className="space-y-2 text-sm">
              <Row icon={<Server size={13} />} label="Config Item">{incident.configuration_item ?? '—'}</Row>
              <Row label="Business Service">{incident.business_service ?? '—'}</Row>
            </dl>
          </Card>

          <Card title="Timestamps">
            <dl className="space-y-2 text-sm">
              <Row icon={<Clock size={13} />} label="Created">
                {new Date(incident.created_at).toLocaleString()}
              </Row>
              <Row label="Updated">
                {new Date(incident.updated_at).toLocaleString()}
              </Row>
            </dl>
          </Card>
        </div>
      </div>

      {/* Edit Modal */}
      {editOpen && (
        <EditModal
          incident={incident}
          onClose={() => setEditOpen(false)}
          onSave={(data) => updateMut.mutate(data)}
          isSaving={updateMut.isPending}
          saveError={updateMut.error}
        />
      )}

      {/* Triage completion toast — top right */}
      {triagePopup && (
        <div className="fixed top-4 right-4 z-50 w-96">
          <div className="bg-green-400 text-white rounded-lg shadow-xl p-4 flex items-start gap-3">
            <CheckCircle size={18} className="shrink-0 mt-0.5 text-green-300" />
            <div className="flex-1 text-sm">
              <p className="font-semibold leading-snug">Triage Agent</p>
              <p className="text-green-200 text-xs font-medium mt-0.5">Assigned to {triagePopup.assignedTo}</p>
              {triagePopup.assignmentGroup && (
                <p className="text-green-100 text-xs mt-1.5">{triagePopup.assignmentGroup}</p>
              )}
            </div>
            <Spinner size="sm" />
          </div>
        </div>
      )}

      {/* Agent event toasts — newest on top, top-right, professional */}
      <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 w-96 pointer-events-none">
        {toasts.map((toast) => (
          <ToastCard
            key={toast.id}
            toast={toast}
            onDismiss={() => setToasts(prev => prev.filter(t => t.id !== toast.id))}
          />
        ))}
      </div>
    </div>
  )
}

function Card({ title, children }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <div className="px-4 py-2.5 bg-gray-50 border-b border-gray-200">
        <h3 className="text-sm font-semibold text-gray-700">{title}</h3>
      </div>
      <div className="p-4">{children}</div>
    </div>
  )
}

const TOAST_DURATION = 5000 // ms

function ToastCard({ toast, onDismiss }) {
  return (
    <div className="bg-green-700 text-white rounded-lg shadow-xl overflow-hidden pointer-events-auto">
      {/* Content */}
      <div className="flex items-start gap-3 p-4">
        <CheckCircle size={18} className="shrink-0 mt-0.5 text-green-300" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold leading-snug">{toast.title}</p>
          <p className="text-xs text-green-200 mt-0.5 font-medium">{toast.action}</p>
          <p className="text-xs text-green-100 mt-1.5 leading-relaxed line-clamp-2">
            {toast.message.substring(0, 120)}{toast.message.length > 120 ? '…' : ''}
          </p>
        </div>
        <button
          onClick={onDismiss}
          className="shrink-0 ml-1 p-1 rounded hover:bg-green-600 text-green-300 hover:text-white transition-colors"
          title="Dismiss"
        >
          <X size={15} />
        </button>
      </div>
      {/* Progress bar — drains left to right over TOAST_DURATION ms */}
      <div className="h-1 bg-green-900">
        <div
          className="h-1 bg-green-300 origin-left"
          style={{
            animation: `toast-drain ${TOAST_DURATION}ms linear forwards`,
          }}
        />
      </div>
      <style>{`
        @keyframes toast-drain {
          from { transform: scaleX(1); }
          to   { transform: scaleX(0); }
        }
      `}</style>
    </div>
  )
}

const SOURCE_STYLES = {
  TRIAGE_AGENT:          { bg: 'bg-purple-100', text: 'text-purple-700', label: 'Triage Agent' },
  ACKNOWLEDGEMENT_AGENT: { bg: 'bg-blue-100',   text: 'text-blue-700',   label: 'Ack Agent' },
  PENDING_AGENT:         { bg: 'bg-yellow-100', text: 'text-yellow-700', label: 'Pending Agent' },
  RESOLUTION_AGENT:      { bg: 'bg-orange-100', text: 'text-orange-700', label: 'Resolution Agent' },
  ENGINEER:              { bg: 'bg-green-100',  text: 'text-green-700',  label: 'Engineer' },
  USER:                  { bg: 'bg-gray-100',   text: 'text-gray-600',   label: 'User' },
  SYSTEM:                { bg: 'bg-slate-100',  text: 'text-slate-600',  label: 'System' },
}

function WorkNoteEntry({ note }) {
  const style = SOURCE_STYLES[note.source_type] ?? SOURCE_STYLES.SYSTEM
  const time = new Date(note.created_at).toLocaleString()

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full ${style.bg} ${style.text}`}>
            <MessageSquare size={12} />
            {style.label}
          </span>
          <span className="text-sm font-semibold text-gray-800">{note.source_name}</span>
          {note.action_type && (
            <span className="text-xs font-medium text-gray-500 bg-gray-100 px-2 py-1 rounded">
              {note.action_type.replace(/_/g, ' ')}
            </span>
          )}
        </div>
        <span className="text-xs text-gray-400 font-medium">{time}</span>
      </div>
      
      {/* Message */}
      <div className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">{note.message}</div>
    </div>
  )
}
function Row({ label, icon, children }) {
  return (
    <div className="flex items-start justify-between gap-2">
      <dt className="text-gray-500 flex items-center gap-1 shrink-0">
        {icon}{label}
      </dt>
      <dd className="text-gray-800 text-right capitalize">{children}</dd>
    </div>
  )
}

function mapImpact(v) {
  return { '1': 'High', '2': 'Medium', '3': 'Low' }[v] ?? v
}
function mapUrgency(v) {
  return { '1': 'High', '2': 'Medium', '3': 'Low' }[v] ?? v
}

const CATEGORIES = ['network','hardware','software','database','security','access','email','vpn','application','other']
const ASSIGNMENT_GROUPS = [
  "Apps Run - BPM",
  "Apps Run - NON SAP ERP-AS400",
  "Apps Run - NON SAP ERP-INF-INFOR",
  "Apps Run - NON SAP ERP-MS NAV",
  "Apps Run - NON SAP ERP-OAD-LAG",
  "Apps Run - Stat & Tax",
  "Apps Run - User-Admin-JDA/WMS",
  "Apps Run-Ariba",
  "Apps Run-BI-Analytics-SAP BO",
  "Apps Run-BI-Analytics-DataLake",
  "Apps Run-BI-Analytics-PowerBI",
  "Apps Run-BI-Analytics-SAP BW",
  "Apps Run-Christmas",
  "Apps Run-JDE",
  "Apps Run-Kronos",
  "Apps Run-MES",
  "Apps Run-Middleware - EAI",
  "Apps Run-Middleware - EDI/EAI",
  "Apps Run-MyML Operations",
  "Apps Run-OT",
  "Apps Run-SAP - BASIS",
  "Apps Run-SAP - Batch - BASIS",
  "Apps Run-SAP - Development",
  "Apps Run-SAP - FICO",
  "Apps Run-SAP - MM/WM/PP",
  "Apps Run-SAP - PP/QM/PM",
  "Apps Run-SAP - Security/GRC",
  "Apps Run-Supply Chain",
  "Apps Run-PLM",
  "Apps Run-SAP - SD",
  "Apps Run-SFDC",
  "Apps Run-Sun-Corp Apps",
  "Apps Run-MetaStorm",
  "Apps Run-MKT Ecom",
  "Apps Run-SharePoint",
  "Apps Run-Hyperion",
  "Apps Run-NON SAP ERP-XPPS",
  "Apps Run-MTD-SFDC",
  "Apps Run-Digital Ops",
  "Apps Run-Robotic Process Automation",
  "Apps Run-Robotic Process Automation-L",
  "Apps Run-Workday",
  "Grand Total",
  'HCL Apps Run-SAP'
];

const iCls = "w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"

function EditField({ label, children }) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
      {children}
    </div>
  )
}

function EditModal({ incident, onClose, onSave, isSaving, saveError }) {
  const { register, handleSubmit, formState: { errors } } = useForm({
    defaultValues: {
      short_description: incident.short_description ?? '',
      description: incident.description ?? '',
      work_notes: incident.work_notes ?? '',
      comments: incident.comments ?? '',
      priority: incident.priority ?? '3',
      state: incident.state ?? 'new',
      category: incident.category ?? '',
      subcategory: incident.subcategory ?? '',
      impact: incident.impact ?? '2',
      urgency: incident.urgency ?? '2',
      assignment_group: incident.assignment_group ?? '',
      assigned_to: incident.assigned_to ?? '',
      caller: incident.caller ?? '',
      configuration_item: incident.configuration_item ?? '',
      business_service: incident.business_service ?? '',
      environment: incident.environment ?? '',
    },
  })

  const onSubmit = (data) => {
    const cleaned = Object.fromEntries(
      Object.entries(data).map(([k, v]) => [k, v === '' ? null : v])
    )
    onSave(cleaned)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 overflow-y-auto py-8">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl mx-4">
        {/* Modal header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
          <h2 className="text-base font-semibold text-gray-800">
            Edit {incident.incident_number}
          </h2>
          <button onClick={onClose} className="p-1 text-gray-400 hover:text-gray-600 rounded">
            <X size={18} />
          </button>
        </div>

        {/* Error */}
        {saveError && (
          <div className="mx-5 mt-4 bg-red-50 border border-red-200 text-red-700 rounded px-3 py-2 text-sm">
            {saveError?.response?.data?.detail ?? saveError?.message}
          </div>
        )}

        <form onSubmit={handleSubmit(onSubmit)}>
          <div className="p-5 space-y-4">
            {/* Core */}
            <EditField label="Short Description *">
              <input
                {...register('short_description', { required: true, minLength: 5 })}
                className={iCls + (errors.short_description ? ' border-red-400' : '')}
              />
              {errors.short_description && (
                <p className="text-xs text-red-500 mt-0.5">Minimum 5 characters required</p>
              )}
            </EditField>

            <EditField label="Description">
              <textarea {...register('description')} rows={3} className={iCls + ' resize-none'} />
            </EditField>

            <EditField label="Work Notes">
              <textarea {...register('work_notes')} rows={2} className={iCls + ' resize-none'} />
            </EditField>

            <EditField label="Comments">
              <textarea {...register('comments')} rows={2} className={iCls + ' resize-none'} />
            </EditField>

            {/* Classification */}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <EditField label="Priority">
                <select {...register('priority')} className={iCls}>
                  <option value="1">1 - Critical</option>
                  <option value="2">2 - High</option>
                  <option value="3">3 - Medium</option>
                  <option value="4">4 - Low</option>
                </select>
              </EditField>

              <EditField label="State">
                <select {...register('state')} className={iCls}>
                  <option value="new">New</option>
                  <option value="in_progress">Active</option>
                  <option value="on_hold">Pending</option>
                  <option value="resolved">Resolved</option>
                  <option value="closed">Closed</option>
                  <option value="cancelled">Cancelled</option>
                </select>
              </EditField>

              <EditField label="Category">
                <select {...register('category')} className={iCls}>
                  <option value="">— None —</option>
                  {CATEGORIES.map(c => (
                    <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>
                  ))}
                </select>
              </EditField>

              <EditField label="Subcategory">
                <input {...register('subcategory')} className={iCls} placeholder="e.g. SMTP" />
              </EditField>

              <EditField label="Impact">
                <select {...register('impact')} className={iCls}>
                  <option value="1">High</option>
                  <option value="2">Medium</option>
                  <option value="3">Low</option>
                </select>
              </EditField>

              <EditField label="Urgency">
                <select {...register('urgency')} className={iCls}>
                  <option value="1">High</option>
                  <option value="2">Medium</option>
                  <option value="3">Low</option>
                </select>
              </EditField>

              <EditField label="Environment">
                <select {...register('environment')} className={iCls}>
                  <option value="">— None —</option>
                  <option value="production">Production</option>
                  <option value="staging">Staging</option>
                  <option value="development">Development</option>
                  <option value="dr">DR</option>
                </select>
              </EditField>
            </div>

            {/* Assignment */}
            <div className="grid grid-cols-2 gap-3">
              <EditField label="Assignment Group">
                <select {...register('assignment_group')} className={iCls}>
                  <option value="">— Unassigned —</option>
                  {/* Show current value as option even if not in the standard list */}
                  {incident.assignment_group && !ASSIGNMENT_GROUPS.includes(incident.assignment_group) && (
                    <option value={incident.assignment_group}>{incident.assignment_group}</option>
                  )}
                  {ASSIGNMENT_GROUPS.map(g => (
                    <option key={g} value={g}>{g}</option>
                  ))}
                </select>
              </EditField>

              <EditField label="Assigned To">
                <input {...register('assigned_to')} className={iCls} placeholder="Engineer name" />
              </EditField>

              <EditField label="Caller">
                <input {...register('caller')} className={iCls} placeholder="Reporter name" />
              </EditField>
            </div>

            {/* CMDB */}
            <div className="grid grid-cols-2 gap-3">
              <EditField label="Configuration Item">
                <input {...register('configuration_item')} className={iCls} placeholder="e.g. server-prod-01" />
              </EditField>
              <EditField label="Business Service">
                <input {...register('business_service')} className={iCls} placeholder="e.g. Customer Portal" />
              </EditField>
            </div>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-gray-200 bg-gray-50">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded hover:bg-gray-100 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSaving}
              className="flex items-center gap-2 px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded transition-colors disabled:opacity-60"
            >
              {isSaving ? <Spinner size="sm" /> : null}
              {isSaving ? 'Saving…' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
